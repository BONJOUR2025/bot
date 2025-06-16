from datetime import datetime
from fastapi import APIRouter
from typing import Optional

from app.schemas.payout import Payout, PayoutCreate, PayoutUpdate
from app.services.payout_service import PayoutService


def create_payout_router(service: PayoutService) -> APIRouter:
    router = APIRouter(prefix="/payouts", tags=["Payouts"])

    @router.get("/", response_model=list[Payout])
    async def list_payouts(
        employee_id: Optional[str] = None,
        type: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ):
        return await service.list_payouts(employee_id, type, status, from_date, to_date)

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
            amount=0,
            type="",
            method="",
            status="",
            created_at=datetime.utcnow(),
        )

    return router

