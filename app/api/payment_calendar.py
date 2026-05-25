from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .dependencies import require_permission
from app.data.payment_calendar_repository import (
    PaymentCalendarRepository,
    get_payment_calendar_repository,
)


class ScheduleCreate(BaseModel):
    name: str
    planned_amount: float
    day_of_month: int
    category: str = ""
    responsible_name: str = ""
    responsible_tg_id: str = ""
    notify_days_before: int = 3
    note: str = ""


class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    planned_amount: Optional[float] = None
    day_of_month: Optional[int] = None
    category: Optional[str] = None
    responsible_name: Optional[str] = None
    responsible_tg_id: Optional[str] = None
    notify_days_before: Optional[int] = None
    is_active: Optional[bool] = None
    note: Optional[str] = None


class PayBody(BaseModel):
    actual_amount: Optional[float] = None
    comment: Optional[str] = None


def create_payment_calendar_router(repo: Optional[PaymentCalendarRepository] = None) -> APIRouter:
    if repo is None:
        repo = get_payment_calendar_repository()

    router = APIRouter(prefix="/payment-calendar", tags=["payment-calendar"])
    perm = require_permission("payment-calendar")

    @router.get("/schedules")
    async def list_schedules(_=Depends(perm)):
        return repo.list_schedules()

    @router.post("/schedules")
    async def create_schedule(body: ScheduleCreate, _=Depends(perm)):
        if not 1 <= body.day_of_month <= 31:
            raise HTTPException(400, "day_of_month must be 1–31")
        return repo.create_schedule(body.model_dump())

    @router.patch("/schedules/{schedule_id}")
    async def update_schedule(schedule_id: int, body: ScheduleUpdate, _=Depends(perm)):
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        result = repo.update_schedule(schedule_id, updates)
        if result is None:
            raise HTTPException(404, "not found")
        return result

    @router.delete("/schedules/{schedule_id}")
    async def delete_schedule(schedule_id: int, _=Depends(perm)):
        if not repo.delete_schedule(schedule_id):
            raise HTTPException(404, "not found")
        return {"ok": True}

    @router.get("/month/{year_month}")
    async def get_month(year_month: str, _=Depends(perm)):
        try:
            datetime.strptime(year_month, "%Y-%m")
        except ValueError:
            raise HTTPException(400, "year_month must be YYYY-MM")
        return repo.get_or_create_records_for_month(year_month)

    @router.post("/records/{record_id}/pay")
    async def mark_paid(record_id: int, body: PayBody, _=Depends(perm)):
        updates: dict = {"status": "paid", "paid_at": datetime.utcnow()}
        if body.actual_amount is not None:
            updates["actual_amount"] = body.actual_amount
        if body.comment is not None:
            updates["comment"] = body.comment
        result = repo.update_record(record_id, updates)
        if result is None:
            raise HTTPException(404, "not found")
        return result

    @router.post("/records/{record_id}/skip")
    async def mark_skipped(record_id: int, _=Depends(perm)):
        result = repo.update_record(record_id, {"status": "skipped"})
        if result is None:
            raise HTTPException(404, "not found")
        return result

    @router.post("/records/{record_id}/reset")
    async def reset_record(record_id: int, _=Depends(perm)):
        result = repo.update_record(
            record_id,
            {"status": "pending", "paid_at": None, "actual_amount": None, "comment": None},
        )
        if result is None:
            raise HTTPException(404, "not found")
        return result

    return router
