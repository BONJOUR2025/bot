from __future__ import annotations

from datetime import date
from typing import List

from ..data.employee_repository import EmployeeRepository
from ..schemas.birthday import BirthdayOut


class BirthdayService:
    """Service to work with employee birthdays."""

    def __init__(self, repo: EmployeeRepository) -> None:
        self._repo = repo

    async def upcoming_birthdays(
            self, days_ahead: int = 30) -> List[BirthdayOut]:
        employees = self._repo.list_employees()
        today = date.today()
        items: List[BirthdayOut] = []
        for emp in employees:
            if not emp.birthdate:
                continue
            try:
                next_bday = emp.birthdate.replace(year=today.year)
            except Exception:
                continue
            if next_bday < today:
                next_bday = next_bday.replace(year=today.year + 1)
            in_days = (next_bday - today).days
            if 0 <= in_days <= days_ahead:
                age = next_bday.year - emp.birthdate.year
                items.append(
                    BirthdayOut(
                        id=emp.id,
                        full_name=emp.full_name or emp.name,
                        birthdate=emp.birthdate.isoformat(),
                        age=age,
                        in_days=in_days,
                    )
                )
        items.sort(key=lambda x: x.in_days)
        return items

    async def all_birthdays(self) -> List[BirthdayOut]:
        """Return birthdays for all employees with countdown in days."""
        employees = self._repo.list_employees()
        today = date.today()
        items: List[BirthdayOut] = []
        for emp in employees:
            if not emp.birthdate:
                continue
            try:
                next_bday = emp.birthdate.replace(year=today.year)
            except Exception:
                continue
            if next_bday < today:
                next_bday = next_bday.replace(year=today.year + 1)
            in_days = (next_bday - today).days
            age = next_bday.year - emp.birthdate.year
            items.append(
                BirthdayOut(
                    id=emp.id,
                    full_name=emp.full_name or emp.name,
                    birthdate=emp.birthdate.isoformat(),
                    age=age,
                    in_days=in_days,
                )
            )

        items.sort(key=lambda x: x.in_days)
        return items
