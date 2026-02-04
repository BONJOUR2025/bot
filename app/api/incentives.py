from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException

from app.schemas.incentive import Incentive, IncentiveCreate, IncentiveUpdate
from app.services.incentive_service import IncentiveService
from app.services.access_control_service import AccessControlService, ResolvedUser

from .dependencies import get_current_user


def create_incentive_router(
    service: IncentiveService, access_service: AccessControlService
) -> APIRouter:
    router = APIRouter(prefix="/incentives", tags=["Incentives"])

    def _filter_incentives(items: List[Incentive], current: ResolvedUser) -> List[Incentive]:
        allowed = access_service.visible_employee_ids(current)
        if allowed is None:
            return items
        return [item for item in items if str(item.employee_id) in allowed]

    def _ensure_incentive_access(item_id: str, current: ResolvedUser) -> None:
        owner = service.get_incentive_employee(item_id)
        if owner is None:
            return
        if not access_service.is_employee_visible(current, owner):
            raise HTTPException(status_code=403, detail="forbidden")

    @router.get("/", response_model=List[Incentive])
    async def list_incentives(
        employee_id: Optional[str] = None,
        type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        current: ResolvedUser = Depends(get_current_user),
    ):
        allowed = access_service.visible_employee_ids(current)
        if allowed is not None and employee_id and employee_id not in allowed:
            return []
        incentives = await service.list_incentives(employee_id, type, date_from, date_to)
        return _filter_incentives(incentives, current)

    @router.post("/", response_model=Incentive)
    async def add_incentive(
        data: IncentiveCreate, current: ResolvedUser = Depends(get_current_user)
    ):
        if not access_service.is_employee_visible(current, data.employee_id):
            raise HTTPException(status_code=403, detail="forbidden")
        return await service.create_incentive(data)

    @router.patch("/{item_id}", response_model=Incentive)
    async def update_incentive(
        item_id: str,
        data: IncentiveUpdate,
        current: ResolvedUser = Depends(get_current_user),
    ):
        _ensure_incentive_access(item_id, current)
        if data.employee_id and not access_service.is_employee_visible(
            current, data.employee_id
        ):
            raise HTTPException(status_code=403, detail="forbidden")
        updated = await service.update_incentive(item_id, data)
        if not updated:
            raise HTTPException(status_code=404, detail="Not found or locked")
        if not access_service.is_employee_visible(current, updated.employee_id):
            raise HTTPException(status_code=403, detail="forbidden")
        return updated

    @router.delete("/{item_id}")
    async def delete_incentive(
        item_id: str, current: ResolvedUser = Depends(get_current_user)
    ):
        _ensure_incentive_access(item_id, current)
        if not await service.delete_incentive(item_id):
            raise HTTPException(status_code=404, detail="Not found or locked")
        return {"status": "deleted"}

    return router
