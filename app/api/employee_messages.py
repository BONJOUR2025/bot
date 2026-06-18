from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.employee_message import (
    EmployeeMessage,
    EmployeeMessageCreate,
    EmployeeMessageReply,
)
from app.services.employee_message_service import EmployeeMessageService
from app.services.access_control_service import AccessControlService, ResolvedUser

from .dependencies import get_current_user

VIEW_PERMISSION = "employee-messages"


def create_employee_message_router(
    service: EmployeeMessageService, access_service: AccessControlService
) -> APIRouter:
    router = APIRouter(prefix="/employee-messages", tags=["EmployeeMessages"])

    def _filter_visible(items: list[EmployeeMessage], current: ResolvedUser) -> list[EmployeeMessage]:
        allowed = access_service.visible_employee_ids(current)
        if allowed is None:
            return items
        return [m for m in items if str(m.employee_id) in allowed]

    def _ensure_access(message_id: str, current: ResolvedUser) -> None:
        owner = service.get_message_employee(message_id)
        if owner is None:
            return
        if not access_service.is_employee_visible(current, owner):
            raise HTTPException(status_code=403, detail="forbidden")

    @router.get("/", response_model=list[EmployeeMessage])
    async def list_messages(
        employee_id: str | None = Query(None),
        current: ResolvedUser = Depends(get_current_user),
    ):
        allowed = access_service.visible_employee_ids(current)
        if allowed is not None and employee_id and employee_id not in allowed:
            return []
        if allowed is not None and not employee_id:
            raise HTTPException(status_code=403, detail="forbidden")
        messages = await service.list_messages(employee_id)
        return _filter_visible(messages, current)

    @router.post("/", response_model=EmployeeMessage)
    async def create_message(
        data: EmployeeMessageCreate, current: ResolvedUser = Depends(get_current_user)
    ):
        if not access_service.is_employee_visible(current, data.employee_id):
            raise HTTPException(status_code=403, detail="forbidden")
        return await service.create_message(data)

    @router.post("/{message_id}/read", response_model=EmployeeMessage)
    async def mark_read(message_id: str, current: ResolvedUser = Depends(get_current_user)):
        if not access_service.user_has_permission(current, VIEW_PERMISSION):
            raise HTTPException(status_code=403, detail="forbidden")
        updated = await service.mark_read(message_id)
        if not updated:
            raise HTTPException(status_code=404, detail="not_found")
        return updated

    @router.post("/{message_id}/reply", response_model=EmployeeMessage)
    async def reply(
        message_id: str,
        body: EmployeeMessageReply,
        current: ResolvedUser = Depends(get_current_user),
    ):
        if not access_service.user_has_permission(current, VIEW_PERMISSION):
            raise HTTPException(status_code=403, detail="forbidden")
        _ensure_access(message_id, current)
        updated = await service.reply(message_id, body.reply)
        if not updated:
            raise HTTPException(status_code=404, detail="not_found")
        return updated

    return router
