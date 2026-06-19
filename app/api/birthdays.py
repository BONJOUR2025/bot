from fastapi import APIRouter, Depends, Query

from app.schemas.birthday import Birthday
from app.services.birthday_service import get_upcoming_birthdays

from .dependencies import require_permission


def create_birthday_router() -> APIRouter:
    router = APIRouter(
        prefix="/birthdays",
        tags=["Birthdays"],
        dependencies=[Depends(require_permission("birthdays"))],
    )

    @router.get("/", response_model=list[Birthday])
    async def list_upcoming(days: int = Query(1, ge=0, le=365)):
        return get_upcoming_birthdays(days)

    return router
