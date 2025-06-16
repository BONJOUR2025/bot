from typing import List

from fastapi import APIRouter, Query

from app.schemas.birthday import BirthdayOut
from app.services.birthday_service import BirthdayService


def create_birthdays_router(service: BirthdayService) -> APIRouter:
    router = APIRouter(prefix="/birthdays", tags=["Birthdays"])

    @router.get("/", response_model=List[BirthdayOut])
    async def list_all():
        return await service.all_birthdays()

    @router.get("/upcoming", response_model=List[BirthdayOut])
    async def upcoming(days_ahead: int = Query(30)):
        return await service.upcoming_birthdays(days_ahead)

    return router
