from fastapi import APIRouter, HTTPException, Query

from app.schemas.asset import Asset, AssetCreate, AssetUpdate
from app.services.asset_service import AssetService


def create_asset_router(service: AssetService) -> APIRouter:
    router = APIRouter(prefix="/assets", tags=["Assets"])

    @router.get("/", response_model=list[Asset])
    async def list_assets(employee_id: str | None = Query(None)):
        return await service.list_assets(employee_id)

    @router.post("/", response_model=Asset)
    async def create_asset(data: AssetCreate):
        return await service.create_asset(data)

    @router.put("/{item_id}", response_model=Asset)
    async def update_asset(item_id: str, data: AssetUpdate):
        asset = await service.update_asset(item_id, data)
        if not asset:
            raise HTTPException(status_code=404, detail="Not found")
        return asset

    @router.delete("/{item_id}")
    async def delete_asset(item_id: str):
        await service.delete_asset(item_id)
        return {"status": "deleted"}

    return router
