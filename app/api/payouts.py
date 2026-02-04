from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.core.enums import PAYOUT_STATUSES
from app.schemas.payout import Payout, PayoutCreate, PayoutUpdate
from app.services.payout_service import PayoutService
from app.services.access_control_service import AccessControlService, ResolvedUser

from .dependencies import get_current_user


MANAGE_DATES_PERMISSION = "payouts-manage-dates"


def create_payout_router(
    service: PayoutService, access_service: AccessControlService
) -> APIRouter:
    router = APIRouter(prefix="/payouts", tags=["Payouts"])

    def _filter_visible(payouts: list[Payout], current: ResolvedUser) -> list[Payout]:
        allowed = access_service.visible_employee_ids(current)
        if allowed is None:
            return payouts
        return [p for p in payouts if str(p.user_id) in allowed]

    def _ensure_access(payout_id: str, current: ResolvedUser) -> None:
        owner = service.get_payout_employee(payout_id)
        if owner is None:
            return
        if not access_service.is_employee_visible(current, owner):
            raise HTTPException(status_code=403, detail="forbidden")

    @router.get("/", response_model=list[Payout])
    async def list_payouts(
        employee_id: Optional[str] = None,
        payout_type: Optional[str] = None,
        status: Optional[str] = None,
        method: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        current: ResolvedUser = Depends(get_current_user),
    ):
        allowed = access_service.visible_employee_ids(current)
        if allowed is not None and employee_id and employee_id not in allowed:
            return []
        payouts = await service.list_payouts(
            employee_id, payout_type, status, method, from_date, to_date
        )
        return _filter_visible(payouts, current)

    @router.get("", response_model=list[Payout], include_in_schema=False)
    async def list_payouts_no_slash(
        employee_id: Optional[str] = None,
        payout_type: Optional[str] = None,
        status: Optional[str] = None,
        method: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        current: ResolvedUser = Depends(get_current_user),
    ):
        allowed = access_service.visible_employee_ids(current)
        if allowed is not None and employee_id and employee_id not in allowed:
            return []
        payouts = await service.list_payouts(
            employee_id, payout_type, status, method, from_date, to_date
        )
        return _filter_visible(payouts, current)

    @router.post("/", response_model=Payout)
    async def create_payout(
        data: PayoutCreate, current: ResolvedUser = Depends(get_current_user)
    ):
        if not access_service.is_employee_visible(current, data.user_id):
            raise HTTPException(status_code=403, detail="forbidden")
        if data.timestamp is not None and not access_service.user_has_permission(
            current, MANAGE_DATES_PERMISSION
        ):
            raise HTTPException(status_code=403, detail="forbidden")
        return await service.create_payout(data)

    @router.put("/{payout_id}", response_model=Payout)
    async def update_payout(
        payout_id: str,
        update: PayoutUpdate,
        current: ResolvedUser = Depends(get_current_user),
    ):
        _ensure_access(payout_id, current)
        if update.timestamp is not None and not access_service.user_has_permission(
            current, MANAGE_DATES_PERMISSION
        ):
            raise HTTPException(status_code=403, detail="forbidden")
        if update.user_id and not access_service.is_employee_visible(
            current, update.user_id
        ):
            raise HTTPException(status_code=403, detail="forbidden")
        updated = await service.update_payout(payout_id, update)
        if updated:
            if not access_service.is_employee_visible(current, updated.user_id):
                raise HTTPException(status_code=403, detail="forbidden")
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
    async def set_status(
        payout_id: str,
        body: PayoutUpdate,
        current: ResolvedUser = Depends(get_current_user),
    ):
        if body.status is None:
            raise HTTPException(status_code=400, detail="status required")
        _ensure_access(payout_id, current)
        notify = True if body.notify_user is None else body.notify_user
        updated = await service.update_status(payout_id, body.status, notify)
        if updated:
            if not access_service.is_employee_visible(current, updated.user_id):
                raise HTTPException(status_code=403, detail="forbidden")
            return updated
        raise HTTPException(status_code=404, detail="not found")

    @router.post("/{payout_id}/approve", response_model=Payout)
    async def approve(
        payout_id: str, current: ResolvedUser = Depends(get_current_user)
    ):
        _ensure_access(payout_id, current)
        updated = await service.update_status(payout_id, PAYOUT_STATUSES[1])
        if updated:
            if not access_service.is_employee_visible(current, updated.user_id):
                raise HTTPException(status_code=403, detail="forbidden")
            return updated
        raise HTTPException(status_code=404, detail="not found")

    @router.post("/{payout_id}/reject", response_model=Payout)
    async def reject(
        payout_id: str, current: ResolvedUser = Depends(get_current_user)
    ):
        _ensure_access(payout_id, current)
        updated = await service.update_status(payout_id, PAYOUT_STATUSES[2])
        if updated:
            if not access_service.is_employee_visible(current, updated.user_id):
                raise HTTPException(status_code=403, detail="forbidden")
            return updated
        raise HTTPException(status_code=404, detail="not found")

    @router.post("/{payout_id}/mark_paid", response_model=Payout)
    async def mark_paid(
        payout_id: str, current: ResolvedUser = Depends(get_current_user)
    ):
        _ensure_access(payout_id, current)
        updated = await service.update_status(payout_id, PAYOUT_STATUSES[3])
        if updated:
            if not access_service.is_employee_visible(current, updated.user_id):
                raise HTTPException(status_code=403, detail="forbidden")
            return updated
        raise HTTPException(status_code=404, detail="not found")

    @router.delete("/{payout_id}")
    async def delete_payout(
        payout_id: str, current: ResolvedUser = Depends(get_current_user)
    ):
        _ensure_access(payout_id, current)
        deleted = await service.delete_payout(payout_id)
        if deleted:
            return {"detail": "deleted"}
        raise HTTPException(status_code=404, detail="not found")

    @router.get("/active", response_model=list[Payout])
    async def list_active_payouts(current: ResolvedUser = Depends(get_current_user)):
        rows = await service.list_active_payouts()
        return _filter_visible(rows, current)

    @router.delete("/")
    async def delete_many(ids: str, current: ResolvedUser = Depends(get_current_user)):
        id_list = [i for i in ids.split(",") if i]
        for payout_id in id_list:
            _ensure_access(payout_id, current)
        await service.delete_payouts(id_list)
        return {"ok": True}

    @router.get("/unconfirmed", response_model=list[Payout])
    async def unconfirmed(current: ResolvedUser = Depends(get_current_user)):
        rows = await service.list_active_payouts()
        return _filter_visible(rows, current)

    @router.get("/export.pdf")
    async def export_pdf(
        employee_id: Optional[str] = None,
        payout_type: Optional[str] = None,
        status: Optional[str] = None,
        method: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        current: ResolvedUser = Depends(get_current_user),
    ):
        allowed = access_service.visible_employee_ids(current)
        if allowed is not None:
            if employee_id:
                if employee_id not in allowed:
                    raise HTTPException(status_code=403, detail="forbidden")
            else:
                raise HTTPException(status_code=403, detail="forbidden")
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
        current: ResolvedUser = Depends(get_current_user),
    ):
        allowed = access_service.visible_employee_ids(current)
        if allowed is not None and employee_id and employee_id not in allowed:
            return []
        result = await service.list_control(
            date_from,
            date_to,
            type,
            method,
            employee_id,
            department,
            status,
        )
        if allowed is not None:
            result = [
                item for item in result if str(item.get("user_id")) in allowed
            ]
        return [{k: v for k, v in item.items() if k != "user_id"} for item in result]

    return router
