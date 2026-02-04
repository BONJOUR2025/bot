from typing import List

from fastapi import APIRouter, Query

from app.schemas.schedule import SchedulePointOut
from app.services.schedule_service import ScheduleService


def create_schedule_router(service: ScheduleService) -> APIRouter:
    router = APIRouter(prefix="/schedule", tags=["Schedule"])

    @router.get("/by_day", response_model=List[SchedulePointOut])
    async def schedule_by_day(date: str = Query(...)):
        return await service.get_schedule_by_day(date)

    return router
