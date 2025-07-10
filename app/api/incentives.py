from typing import List, Optional
from fastapi import APIRouter, HTTPException

from app.schemas.incentive import Incentive, IncentiveCreate, IncentiveUpdate
from app.services.incentive_service import IncentiveService


def create_incentive_router(service: IncentiveService) -> APIRouter:
    router = APIRouter(prefix="/incentives", tags=["Incentives"])

    @router.get("/", response_model=List[Incentive])
    async def list_incentives(
        employee_id: Optional[str] = None,
        type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ):
        return await service.list_incentives(employee_id, type, date_from, date_to)

    @router.post("/", response_model=Incentive)
    async def add_incentive(data: IncentiveCreate):
        return await service.create_incentive(data)

    @router.patch("/{item_id}", response_model=Incentive)
    async def update_incentive(item_id: str, data: IncentiveUpdate):
        updated = await service.update_incentive(item_id, data)
        if not updated:
            raise HTTPException(status_code=404, detail="Not found or locked")
        return updated

    @router.delete("/{item_id}")
    async def delete_incentive(item_id: str):
        if not await service.delete_incentive(item_id):
            raise HTTPException(status_code=404, detail="Not found or locked")
        return {"status": "deleted"}

    return router
