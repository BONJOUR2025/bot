from datetime import date as date_cls
from typing import List

from fastapi import APIRouter, HTTPException, Query

from app.schemas.schedule import SchedulePointOut
from app.services.schedule_service import ScheduleService


def create_schedule_router(service: ScheduleService) -> APIRouter:
    router = APIRouter(prefix="/schedule", tags=["Schedule"])

    @router.get("/by_day", response_model=List[SchedulePointOut])
    async def schedule_by_day(date: str = Query(...)):
        return await service.get_schedule_by_day(date)

    @router.get("/month")
    async def schedule_month(year: int = Query(...), month: int = Query(...)):
        if not (1 <= month <= 12):
            raise HTTPException(status_code=400, detail="month must be 1–12")
        return await service.get_schedule_month(year, month)

    return router
