from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.leave_request import LeaveRequest, LeaveRequestCreate, LeaveRequestStatusUpdate
from app.services.leave_request_service import LeaveRequestService
from app.services.access_control_service import AccessControlService, ResolvedUser

from .dependencies import get_current_user

APPROVE_PERMISSION = "leave-requests"


def create_leave_request_router(
    service: LeaveRequestService, access_service: AccessControlService
) -> APIRouter:
    router = APIRouter(prefix="/leave-requests", tags=["LeaveRequests"])

    def _filter_visible(items: list[LeaveRequest], current: ResolvedUser) -> list[LeaveRequest]:
        allowed = access_service.visible_employee_ids(current)
        if allowed is None:
            return items
        return [r for r in items if str(r.employee_id) in allowed]

    def _ensure_access(request_id: str, current: ResolvedUser) -> None:
        owner = service.get_request_employee(request_id)
        if owner is None:
            return
        if not access_service.is_employee_visible(current, owner):
            raise HTTPException(status_code=403, detail="forbidden")

    @router.get("/", response_model=list[LeaveRequest])
    async def list_requests(
        employee_id: str | None = Query(None),
        current: ResolvedUser = Depends(get_current_user),
    ):
        allowed = access_service.visible_employee_ids(current)
        if allowed is not None and employee_id and employee_id not in allowed:
            return []
        requests = await service.list_requests(employee_id)
        return _filter_visible(requests, current)

    @router.post("/", response_model=LeaveRequest)
    async def create_request(
        data: LeaveRequestCreate, current: ResolvedUser = Depends(get_current_user)
    ):
        if not access_service.is_employee_visible(current, data.employee_id):
            raise HTTPException(status_code=403, detail="forbidden")
        try:
            return await service.create_request(data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/{request_id}/approve", response_model=LeaveRequest)
    async def approve(request_id: str, current: ResolvedUser = Depends(get_current_user)):
        if not access_service.user_has_permission(current, APPROVE_PERMISSION):
            raise HTTPException(status_code=403, detail="forbidden")
        _ensure_access(request_id, current)
        updated = await service.update_status(request_id, "Одобрено")
        if not updated:
            raise HTTPException(status_code=404, detail="not_found")
        return updated

    @router.post("/{request_id}/reject", response_model=LeaveRequest)
    async def reject(request_id: str, current: ResolvedUser = Depends(get_current_user)):
        if not access_service.user_has_permission(current, APPROVE_PERMISSION):
            raise HTTPException(status_code=403, detail="forbidden")
        _ensure_access(request_id, current)
        updated = await service.update_status(request_id, "Отклонено")
        if not updated:
            raise HTTPException(status_code=404, detail="not_found")
        return updated

    @router.put("/{request_id}/status", response_model=LeaveRequest)
    async def set_status(
        request_id: str,
        body: LeaveRequestStatusUpdate,
        current: ResolvedUser = Depends(get_current_user),
    ):
        if not access_service.user_has_permission(current, APPROVE_PERMISSION):
            raise HTTPException(status_code=403, detail="forbidden")
        _ensure_access(request_id, current)
        updated = await service.update_status(request_id, body.status)
        if not updated:
            raise HTTPException(status_code=404, detail="not_found")
        return updated

    @router.delete("/{request_id}")
    async def delete_request(request_id: str, current: ResolvedUser = Depends(get_current_user)):
        _ensure_access(request_id, current)
        await service.delete_request(request_id)
        return {"status": "deleted"}

    return router
