from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from app.data.salon_repository import SalonRepository, get_salon_repository
from app.data.visitor_event_repository import (
    VisitorEventRepository,
    get_visitor_event_repository,
)
from app.schemas.salon import Salon
from app.schemas.visitor_event import VisitorDailySummary, VisitorEventIngest


class VisitorCounterService:
    def __init__(
        self,
        repo: Optional[VisitorEventRepository] = None,
        salon_repo: Optional[SalonRepository] = None,
    ) -> None:
        self._repo = repo or get_visitor_event_repository()
        self._salon_repo = salon_repo or get_salon_repository()

    def get_salon_by_code(self, code: str) -> Optional[Salon]:
        return self._salon_repo.get_by_code(code)

    def record_event(self, data: VisitorEventIngest, salon: Salon) -> dict:
        return self._repo.create(
            {
                "salon_id": salon.id,
                "direction": data.direction,
                "count": data.count,
                "device_id": data.device_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def list_events(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        salon_id: Optional[str] = None,
    ) -> list[dict]:
        return self._repo.list(date_from=date_from, date_to=date_to, salon_id=salon_id)

    def daily_summary(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        salon_id: Optional[str] = None,
    ) -> list[VisitorDailySummary]:
        events = self._repo.list(date_from=date_from, date_to=date_to, salon_id=salon_id)
        totals: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"in": 0, "out": 0})
        for event in events:
            date = str(event.get("created_at", ""))[:10]
            key = (date, str(event.get("salon_id") or ""))
            totals[key][event.get("direction")] += int(event.get("count", 1))

        salons = {s.id: s.name for s in self._salon_repo.list_salons()}
        result = [
            VisitorDailySummary(
                date=date,
                salon_id=sid,
                salon_name=salons.get(sid),
                in_count=counts["in"],
                out_count=counts["out"],
                net=counts["in"] - counts["out"],
            )
            for (date, sid), counts in totals.items()
        ]
        result.sort(key=lambda s: (s.date, s.salon_name or s.salon_id), reverse=True)
        return result


_service: VisitorCounterService | None = None


def get_visitor_counter_service() -> VisitorCounterService:
    global _service
    if _service is None:
        _service = VisitorCounterService()
    return _service
