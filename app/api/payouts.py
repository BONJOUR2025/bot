from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.enums import PAYOUT_STATUSES
from app.schemas.payout import Payout, PayoutCreate, PayoutUpdate
from app.services.payout_service import PayoutService


def create_payout_router(service: PayoutService) -> APIRouter:
    router = APIRouter(prefix="/payouts", tags=["Payouts"])

    @router.get("/", response_model=list[Payout])
    async def list_payouts(
        employee_id: Optional[str] = None,
        payout_type: Optional[str] = None,
        status: Optional[str] = None,
        method: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ):
        return await service.list_payouts(employee_id, payout_type, status, method, from_date, to_date)

    @router.get("", response_model=list[Payout], include_in_schema=False)
    async def list_payouts_no_slash(
        employee_id: Optional[str] = None,
        payout_type: Optional[str] = None,
        status: Optional[str] = None,
        method: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ):
        return await service.list_payouts(employee_id, payout_type, status, method, from_date, to_date)

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
            timestamp=None,
        )

    @router.put("/{payout_id}/status", response_model=Payout)
    async def set_status(payout_id: str, body: PayoutUpdate):
        if body.status is None:
            raise HTTPException(status_code=400, detail="status required")
        notify = True if body.notify_user is None else body.notify_user
        updated = await service.update_status(payout_id, body.status, notify)
        if updated:
            return updated
        raise HTTPException(status_code=404, detail="not found")

    @router.post("/{payout_id}/approve", response_model=Payout)
    async def approve(payout_id: str):
        updated = await service.update_status(payout_id, PAYOUT_STATUSES[1])
        if updated:
            return updated
        raise HTTPException(status_code=404, detail="not found")

    @router.post("/{payout_id}/reject", response_model=Payout)
    async def reject(payout_id: str):
        updated = await service.update_status(payout_id, PAYOUT_STATUSES[2])
        if updated:
            return updated
        raise HTTPException(status_code=404, detail="not found")

    @router.post("/{payout_id}/mark_paid", response_model=Payout)
    async def mark_paid(payout_id: str):
        updated = await service.update_status(payout_id, PAYOUT_STATUSES[3])
        if updated:
            return updated
        raise HTTPException(status_code=404, detail="not found")

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

    @router.get("/unconfirmed", response_model=list[Payout])
    async def unconfirmed():
        rows = await service.list_active_payouts()
        return rows

    @router.get("/export.pdf")
    async def export_pdf(
        employee_id: Optional[str] = None,
        payout_type: Optional[str] = None,
        status: Optional[str] = None,
        method: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ):
        path = await service.export_to_pdf(
            employee_id, payout_type, status, method, from_date, to_date
        )
        if path:
            return FileResponse(Path(path), filename=Path(path).name)
        raise HTTPException(status_code=404, detail="No data")

    @router.get("/control")
    async def payouts_control(
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        type: Optional[str] = None,
        method: Optional[str] = None,
        employee_id: Optional[str] = None,
        department: Optional[str] = None,
        status: Optional[str] = None,
    ):
        return await service.list_control(
            date_from,
            date_to,
            type,
            method,
            employee_id,
            department,
            status,
        )

    return router
