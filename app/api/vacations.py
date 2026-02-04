from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.vacation import Vacation, VacationCreate, VacationUpdate
from app.services.vacation_service import VacationService
from app.services.access_control_service import AccessControlService, ResolvedUser

from .dependencies import get_current_user


def create_vacation_router(
    service: VacationService, access_service: AccessControlService
) -> APIRouter:
    router = APIRouter(prefix="/vacations", tags=["Vacations"])

    def _filter_vacations(items: list[Vacation], current: ResolvedUser) -> list[Vacation]:
        allowed = access_service.visible_employee_ids(current)
        if allowed is None:
            return items
        return [vac for vac in items if str(vac.employee_id) in allowed]

    def _ensure_vacation_access(vac_id: str, current: ResolvedUser) -> None:
        owner = service.get_vacation_employee(vac_id)
        if owner is None:
            return
        if not access_service.is_employee_visible(current, owner):
            raise HTTPException(status_code=403, detail="forbidden")

    @router.get("/", response_model=list[Vacation])
    async def list_vacations(
        employee_id: str | None = Query(None),
        type: str | None = Query(None),
        date_from: str | None = Query(None),
        date_to: str | None = Query(None),
        current: ResolvedUser = Depends(get_current_user),
    ):
        allowed = access_service.visible_employee_ids(current)
        if allowed is not None and employee_id and employee_id not in allowed:
            return []
        vacations = await service.list_vacations(employee_id, type, date_from, date_to)
        return _filter_vacations(vacations, current)

    @router.post("/", response_model=Vacation)
    async def create_vacation(
        data: VacationCreate, current: ResolvedUser = Depends(get_current_user)
    ):
        if not access_service.is_employee_visible(current, data.employee_id):
            raise HTTPException(status_code=403, detail="forbidden")
        try:
            return await service.create_vacation(data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.put("/{vacation_id}", response_model=Vacation)
    async def update_vacation(
        vacation_id: str,
        data: VacationUpdate,
        current: ResolvedUser = Depends(get_current_user),
    ):
        _ensure_vacation_access(vacation_id, current)
        if data.employee_id and not access_service.is_employee_visible(
            current, data.employee_id
        ):
            raise HTTPException(status_code=403, detail="forbidden")
        try:
            vac = await service.update_vacation(vacation_id, data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not vac:
            raise HTTPException(status_code=404, detail="Vacation not found")
        if not access_service.is_employee_visible(current, vac.employee_id):
            raise HTTPException(status_code=403, detail="forbidden")
        return vac

    @router.delete("/{vacation_id}")
    async def delete_vacation(
        vacation_id: str, current: ResolvedUser = Depends(get_current_user)
    ):
        _ensure_vacation_access(vacation_id, current)
        await service.delete_vacation(vacation_id)
        return {"status": "deleted"}

    @router.get("/active", response_model=list[Vacation])
    async def active_vacations(current: ResolvedUser = Depends(get_current_user)):
        vacations = await service.list_active()
        return _filter_vacations(vacations, current)

    @router.get("/reminders", response_model=list[Vacation])
    async def vacation_reminders(current: ResolvedUser = Depends(get_current_user)):
        vacations = await service.list_tomorrow()
        return _filter_vacations(vacations, current)

    return router
