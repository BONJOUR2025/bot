from typing import List

from fastapi import APIRouter, HTTPException

from app.services.adjustment_service import AdjustmentService
from app.schemas.adjustment import Adjustment


def create_adjustment_router(service: AdjustmentService) -> APIRouter:
    router = APIRouter(prefix="/adjustments", tags=["adjustments"])

    @router.get("/", response_model=List[Adjustment])
    async def list_adjustments() -> List[Adjustment]:
        return [Adjustment(**a) for a in service.list()]

    @router.post("/", response_model=Adjustment)
    async def add_adjustment(item: Adjustment) -> Adjustment:
        data = service.create(item.dict(exclude_none=True))
        return Adjustment(**data)

    @router.put("/{adj_id}", response_model=Adjustment)
    async def update_adjustment(adj_id: str, item: Adjustment) -> Adjustment:
        data = service.update(adj_id, item.dict(exclude_none=True))
        if not data:
            raise HTTPException(status_code=404, detail="Not found")
        return Adjustment(**data)

    @router.delete("/{adj_id}")
    async def delete_adjustment(adj_id: str) -> None:
        service.delete(adj_id)
        return {"status": "ok"}

    return router
