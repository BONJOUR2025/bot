from fastapi import APIRouter, Query

from app.services.inventory_service import InventoryService


def create_inventory_router(service: InventoryService) -> APIRouter:
    router = APIRouter(prefix="/inventory", tags=["Inventory"])

    @router.get("/available")
    async def available(item_name: str, size: str | None = Query(None)):
        free = await service.available(item_name, size)
        return {"free": free}

    return router
