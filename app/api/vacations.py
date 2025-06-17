from fastapi import APIRouter, HTTPException

from app.schemas.vacation import Vacation, VacationCreate, VacationUpdate
from app.services.vacation_service import VacationService


def create_vacation_router(service: VacationService) -> APIRouter:
    router = APIRouter(prefix="/vacations", tags=["Vacations"])

    @router.get("/", response_model=list[Vacation])
    async def list_vacations():
        return await service.list_vacations()

    @router.post("/", response_model=Vacation)
    async def create_vacation(data: VacationCreate):
        return await service.create_vacation(data)

    @router.put("/{vacation_id}", response_model=Vacation)
    async def update_vacation(vacation_id: str, data: VacationUpdate):
        vac = await service.update_vacation(vacation_id, data)
        if not vac:
            raise HTTPException(status_code=404, detail="Vacation not found")
        return vac

    @router.delete("/{vacation_id}")
    async def delete_vacation(vacation_id: str):
        await service.delete_vacation(vacation_id)
        return {"status": "deleted"}

    return router
