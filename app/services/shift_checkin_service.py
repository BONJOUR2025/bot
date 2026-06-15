from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from app.data.employee_repository import EmployeeRepository
from app.data.incentive_repository import IncentiveRepository
from app.data.salon_repository import SalonRepository, get_salon_repository
from app.data.shift_checkin_repository import ShiftCheckinRepository, get_shift_checkin_repository
from app.schemas.salon import Salon
from app.schemas.schedule import SchedulePointOut
from app.services.schedule_service import ScheduleService
from app.services.work_hours import MOSCOW_TZ

# Late thresholds, in minutes, and the corresponding penalty amounts (rubles)
LATE_THRESHOLDS = [
    (10, 150),
    (25, 500),
]
LATE_PENALTY_OVER = 1500

_HOURS_SPLIT_RE = re.compile(r"[-–—]")


class ShiftCheckinService:
    def __init__(
        self,
        repo: Optional[ShiftCheckinRepository] = None,
        salon_repo: Optional[SalonRepository] = None,
        schedule_service: Optional[ScheduleService] = None,
        incentive_repo: Optional[IncentiveRepository] = None,
        employee_repo: Optional[EmployeeRepository] = None,
    ) -> None:
        self._repo = repo or get_shift_checkin_repository()
        self._salons = salon_repo or get_salon_repository()
        self._schedule = schedule_service or ScheduleService()
        self._incentives = incentive_repo or IncentiveRepository()
        self._employees = employee_repo or EmployeeRepository()

    async def find_point_for_employee(self, employee_name: str, day: date) -> Optional[SchedulePointOut]:
        """Find which point the employee is scheduled at on the given day."""
        name = (employee_name or "").strip().lower()
        if not name:
            return None
        points = await self._schedule.get_schedule_by_day(day.isoformat())
        for point in points:
            if point.employee.strip().lower() == name:
                return point
        return None

    async def find_point_for_employee_id(self, employee_id: str, day: date) -> Optional[SchedulePointOut]:
        """Find which point the employee is scheduled at, looked up by employee id.

        The schedule (Excel "ИМЯ" column) is matched against the employee's short
        ``name`` field — the same field used by the personal schedule lookup —
        not ``full_name``.
        """
        employee = self._employees.get_employee(employee_id)
        if not employee:
            return None
        return await self.find_point_for_employee(employee.name, day)

    def find_salon_by_code(self, code: str) -> Optional[Salon]:
        code = (code or "").strip().upper()
        if not code:
            return None
        for salon in self._salons.list_salons():
            if salon.code.strip().upper() == code:
                return salon
        return None

    @staticmethod
    def _parse_opening_time(hours: str) -> Optional[tuple[int, int]]:
        parts = _HOURS_SPLIT_RE.split(hours.strip())
        if not parts or not parts[0].strip():
            return None
        try:
            h, m = parts[0].strip().split(":")
            return int(h), int(m)
        except Exception:
            return None

    def compute_penalty(self, sent_at: datetime, salon: Salon) -> tuple[Optional[str], int, float]:
        """Compare sent_at (Moscow time) against the salon's opening time.

        Returns (expected_open_time "HH:MM" or None, delay_minutes, penalty_amount).
        """
        is_weekend = sent_at.weekday() >= 5
        hours = salon.work_hours_weekend if is_weekend else salon.work_hours_weekday
        parsed = self._parse_opening_time(hours or "")
        if parsed is None:
            return None, 0, 0
        h, m = parsed
        expected = sent_at.replace(hour=h, minute=m, second=0, microsecond=0)
        expected_str = f"{h:02d}:{m:02d}"

        delay = int((sent_at - expected).total_seconds() // 60)
        if delay <= 0:
            return expected_str, 0, 0

        penalty = LATE_PENALTY_OVER
        for threshold_minutes, amount in LATE_THRESHOLDS:
            if delay <= threshold_minutes:
                penalty = amount
                break
        return expected_str, delay, penalty

    async def record_checkin(
        self,
        employee_id: str,
        employee_name: str,
        sent_at: datetime,
        photo_path: Optional[str] = None,
        manual: bool = False,
        added_by: str = "bot",
    ) -> dict:
        sent_at = sent_at.astimezone(MOSCOW_TZ)
        today = sent_at.date()

        point = await self.find_point_for_employee_id(employee_id, today)
        salon = self.find_salon_by_code(point.short) if point else None

        expected_open_time: Optional[str] = None
        delay_minutes = 0
        penalty_amount: float = 0
        if salon:
            expected_open_time, delay_minutes, penalty_amount = self.compute_penalty(sent_at, salon)

        record = self._repo.create({
            "employee_id": employee_id,
            "employee_name": employee_name,
            "date": today.isoformat(),
            "point": point.point if point else None,
            "point_short": point.short if point else None,
            "salon_id": salon.id if salon else None,
            "salon_name": salon.name if salon else None,
            "sent_at": sent_at.isoformat(),
            "expected_open_time": expected_open_time,
            "delay_minutes": delay_minutes,
            "penalty_amount": penalty_amount,
            "incentive_id": None,
            "photo_path": photo_path,
            "no_schedule": point is None,
            "manual": manual,
        })

        if penalty_amount > 0:
            incentive = self._incentives.create({
                "employee_id": employee_id,
                "name": employee_name,
                "type": "penalty",
                "amount": penalty_amount,
                "reason": (
                    f"Опоздание открытия точки «{salon.name}» на {delay_minutes} мин "
                    f"(чек отправлен в {sent_at.strftime('%H:%M')}, открытие в {expected_open_time})"
                ),
                "date": today.isoformat(),
                "added_by": added_by,
            })
            record = self._repo.update(record["id"], {"incentive_id": incentive["id"]}) or record

        return record


_service: ShiftCheckinService | None = None


def get_shift_checkin_service() -> ShiftCheckinService:
    global _service
    if _service is None:
        _service = ShiftCheckinService()
    return _service
