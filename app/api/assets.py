from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.asset import Asset, AssetCreate, AssetUpdate
from app.services.asset_service import AssetService
from app.services.access_control_service import AccessControlService, ResolvedUser

from .dependencies import get_current_user


def create_asset_router(
    service: AssetService, access_service: AccessControlService
) -> APIRouter:
    router = APIRouter(prefix="/assets", tags=["Assets"])

    def _filter_assets(items: list[Asset], current: ResolvedUser) -> list[Asset]:
        allowed = access_service.visible_employee_ids(current)
        if allowed is None:
            return items
        return [asset for asset in items if str(asset.employee_id) in allowed]

    def _ensure_asset_access(item_id: str, current: ResolvedUser) -> None:
        owner = service.get_asset_employee(item_id)
        if owner is None:
            return
        if not access_service.is_employee_visible(current, owner):
            raise HTTPException(status_code=403, detail="forbidden")

    @router.get("/", response_model=list[Asset])
    async def list_assets(
        employee_id: str | None = Query(None),
        current: ResolvedUser = Depends(get_current_user),
    ):
        allowed = access_service.visible_employee_ids(current)
        if allowed is not None and employee_id and employee_id not in allowed:
            return []
        assets = await service.list_assets(employee_id)
        return _filter_assets(assets, current)

    @router.post("/", response_model=Asset)
    async def create_asset(
        data: AssetCreate, current: ResolvedUser = Depends(get_current_user)
    ):
        if not access_service.is_employee_visible(current, data.employee_id):
            raise HTTPException(status_code=403, detail="forbidden")
        return await service.create_asset(data)

    @router.put("/{item_id}", response_model=Asset)
    async def update_asset(
        item_id: str,
        data: AssetUpdate,
        current: ResolvedUser = Depends(get_current_user),
    ):
        _ensure_asset_access(item_id, current)
        if data.employee_id and not access_service.is_employee_visible(
            current, data.employee_id
        ):
            raise HTTPException(status_code=403, detail="forbidden")
        asset = await service.update_asset(item_id, data)
        if not asset:
            raise HTTPException(status_code=404, detail="Not found")
        if not access_service.is_employee_visible(current, asset.employee_id):
            raise HTTPException(status_code=403, detail="forbidden")
        return asset

    @router.delete("/{item_id}")
    async def delete_asset(
        item_id: str, current: ResolvedUser = Depends(get_current_user)
    ):
        _ensure_asset_access(item_id, current)
        await service.delete_asset(item_id)
        return {"status": "deleted"}

    return router
