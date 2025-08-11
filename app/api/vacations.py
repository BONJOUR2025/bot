from fastapi import APIRouter, HTTPException, Query

from app.schemas.vacation import Vacation, VacationCreate, VacationUpdate
from app.services.vacation_service import VacationService


def create_vacation_router(service: VacationService) -> APIRouter:
    router = APIRouter(prefix="/vacations", tags=["Vacations"])

    @router.get("/", response_model=list[Vacation])
    async def list_vacations(
        employee_id: str | None = Query(None),
        type: str | None = Query(None),
        date_from: str | None = Query(None),
        date_to: str | None = Query(None),
    ):
        return await service.list_vacations(employee_id, type, date_from, date_to)

    @router.post("/", response_model=Vacation)
    async def create_vacation(data: VacationCreate):
        try:
            return await service.create_vacation(data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.put("/{vacation_id}", response_model=Vacation)
    async def update_vacation(vacation_id: str, data: VacationUpdate):
        try:
            vac = await service.update_vacation(vacation_id, data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not vac:
            raise HTTPException(status_code=404, detail="Vacation not found")
        return vac

    @router.delete("/{vacation_id}")
    async def delete_vacation(vacation_id: str):
        await service.delete_vacation(vacation_id)
        return {"status": "deleted"}

    @router.get("/active", response_model=list[Vacation])
    async def active_vacations():
        return await service.list_active()

    @router.get("/reminders", response_model=list[Vacation])
    async def vacation_reminders():
        return await service.list_tomorrow()

    return router
