from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import require_permission
from app.data.employee_repository import EmployeeRepository
from app.data.vk_bot_user_repository import VkBotUserRepository
from app.schemas.vk_bot_user import VkBotUserLinkRequest, VkBotUserOut
from app.services.access_control_service import ResolvedUser


def create_vk_bot_users_router(repo: VkBotUserRepository) -> APIRouter:
    router = APIRouter(prefix="/vk-bot-users", tags=["VkBotUsers"])

    @router.get("/", response_model=list[VkBotUserOut])
    async def list_vk_bot_users(
        current: ResolvedUser = Depends(require_permission("access")),
    ):
        employees = EmployeeRepository()
        result = []
        for item in repo.list():
            employee = employees.get_by_vk_id(item["vk_id"])
            result.append({
                **item,
                "employee_id": employee.id if employee else None,
                "employee_name": (employee.full_name or employee.name) if employee else None,
            })
        return result

    @router.post("/{vk_id}/link", response_model=VkBotUserOut)
    async def link_vk_bot_user(
        vk_id: str,
        payload: VkBotUserLinkRequest,
        current: ResolvedUser = Depends(require_permission("access")),
    ):
        employees = EmployeeRepository()
        if employees.get_by_vk_id(vk_id):
            raise HTTPException(status_code=400, detail="already_linked")
        # Unlike Telegram, VK is a secondary channel on an existing profile —
        # employee.id (Telegram identity, or the nb_... stub id) is left
        # untouched, only employee.vk_id is set, so nothing else needs
        # reassigning.
        employee = employees.link_vk_id(payload.employee_id, vk_id)
        if not employee:
            raise HTTPException(status_code=404, detail="employee_not_found")

        item = next((u for u in repo.list() if u["vk_id"] == vk_id), None)
        return {
            **(item or {"vk_id": vk_id}),
            "employee_id": employee.id,
            "employee_name": employee.full_name or employee.name,
        }

    @router.post("/{vk_id}/unlink", response_model=VkBotUserOut)
    async def unlink_vk_bot_user(
        vk_id: str,
        current: ResolvedUser = Depends(require_permission("access")),
    ):
        employees = EmployeeRepository()
        employee = employees.get_by_vk_id(vk_id)
        if not employee:
            raise HTTPException(status_code=404, detail="not_linked")
        employees.unlink_vk_id(employee.id)

        item = next((u for u in repo.list() if u["vk_id"] == vk_id), None)
        return {**(item or {"vk_id": vk_id}), "employee_id": None, "employee_name": None}

    return router
