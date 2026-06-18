from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.api.dependencies import require_permission
from app.settings import settings
from app.schemas.visitor_event import VisitorDailySummary, VisitorEvent, VisitorEventIngest
from app.services.visitor_counter_service import VisitorCounterService


def _current_api_key() -> str:
    # Read fresh from config.json so a key saved via the admin UI takes effect
    # immediately, without requiring a server restart (mirrors other settings
    # such as PAYROLL_EXCEL_FILE — see app/api/system.py::_get_payroll_excel_path).
    try:
        data = json.loads(Path("config.json").read_text(encoding="utf-8"))
        if key := data.get("VISITOR_COUNTER_API_KEY"):
            return str(key)
    except Exception:
        pass
    return settings.visitor_counter_api_key


def _check_device_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> None:
    expected = _current_api_key()
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid_api_key")


def create_visitor_counter_device_router(service: VisitorCounterService) -> APIRouter:
    """Public-facing router for counter devices (ESP8266 etc). Protected by a static API key, not a user session."""
    router = APIRouter(prefix="/visitor-events", tags=["VisitorCounters"])

    @router.post("/ingest", status_code=201)
    async def ingest_visitor_event(
        data: VisitorEventIngest,
        _: None = Depends(_check_device_api_key),
    ) -> dict[str, str]:
        salon = service.get_salon_by_code(data.salon_code)
        if not salon:
            raise HTTPException(status_code=404, detail="salon_not_found")
        service.record_event(data, salon)
        return {"status": "ok"}

    return router


def create_visitor_counter_router(service: VisitorCounterService) -> APIRouter:
    router = APIRouter(prefix="/visitor-events", tags=["VisitorCounters"])

    @router.get("/", response_model=list[VisitorEvent])
    async def list_visitor_events(
        date_from: Optional[str] = Query(None),
        date_to: Optional[str] = Query(None),
        salon_id: Optional[str] = Query(None),
        current=Depends(require_permission("visitor-counters")),
    ):
        return service.list_events(date_from=date_from, date_to=date_to, salon_id=salon_id)

    @router.get("/summary", response_model=list[VisitorDailySummary])
    async def visitor_events_summary(
        date_from: Optional[str] = Query(None),
        date_to: Optional[str] = Query(None),
        salon_id: Optional[str] = Query(None),
        current=Depends(require_permission("visitor-counters")),
    ):
        return service.daily_summary(date_from=date_from, date_to=date_to, salon_id=salon_id)

    return router
