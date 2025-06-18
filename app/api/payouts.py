from fastapi import APIRouter, HTTPException
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

    @router.put("/{payout_id}", response_model=Payout)
    async def update_payout(payout_id: str, update: PayoutUpdate):
        updated = await service.update_payout(payout_id, update)
        if updated:
            return updated
        return Payout(
            id=payout_id,
            user_id="",
            name="",
            phone="",
            bank="",
            amount=0.0,
            method="",
            payout_type="",
            status="",
            timestamp="")

    @router.delete("/{payout_id}")
    async def delete_payout(payout_id: str):
        deleted = await service.delete_payout(payout_id)
        if deleted:
            return {"detail": "deleted"}
        raise HTTPException(status_code=404, detail="not found")

    @router.get("/active", response_model=list[Payout])
    async def list_active_payouts():
        rows = await service.list_active_payouts()
        return rows

    @router.delete("/")
    async def delete_many(ids: str):
        id_list = [i for i in ids.split(",") if i]
        await service.delete_payouts(id_list)
        return {"ok": True}

    return router
