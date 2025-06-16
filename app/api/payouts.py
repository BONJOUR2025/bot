from fastapi import APIRouter
from typing import Optional

from app.schemas.payout import Payout, PayoutCreate, PayoutUpdate
from app.services.payout_service import PayoutService


def create_payout_router(service: PayoutService) -> APIRouter:
    router = APIRouter(prefix="/payouts", tags=["Payouts"])

    @router.get("/", response_model=list[Payout])
    async def list_payouts(
        employee_id: Optional[str] = None,
        payout_type: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ):
        return await service.list_payouts(employee_id, payout_type, status, from_date, to_date)

    @router.post("/", response_model=Payout)
    async def create_payout(data: PayoutCreate):
        return await service.create_payout(data)

    @router.put("/{idx}", response_model=Payout)
    async def update_payout(idx: int, update: PayoutUpdate):
        updated = await service.update_payout(idx, update)
        if updated:
            return updated
        return Payout(idx=idx, user_id="", name="", phone="", bank="", amount=0.0, method="", payout_type="", status="", timestamp="")

    @router.delete("/{idx}")
    async def delete_payout(idx: int):
        await service.delete_payouts([idx])
        return {"ok": True}

    @router.delete("/")
    async def delete_many(indices: str):
        idxs = [int(i) for i in indices.split(",") if i]
        await service.delete_payouts(idxs)
        return {"ok": True}

    return router

