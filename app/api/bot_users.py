from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import require_permission
from app.data.asset_repository import AssetRepository
from app.data.bot_user_repository import BotUserRepository
from app.data.employee_repository import EmployeeRepository
from app.data.incentive_repository import IncentiveRepository
from app.data.payout_repository import PayoutRepository
from app.data.shift_checkin_repository import get_shift_checkin_repository
from app.data.vacation_repository import VacationRepository
from app.schemas.bot_user import BotUserLinkRequest, BotUserOut
from app.services.access_control_service import ResolvedUser


def create_bot_users_router(repo: BotUserRepository) -> APIRouter:
    router = APIRouter(prefix="/bot-users", tags=["BotUsers"])

    @router.get("/", response_model=list[BotUserOut])
    async def list_bot_users(
        current: ResolvedUser = Depends(require_permission("access")),
    ):
        employees = EmployeeRepository()
        result = []
        for item in repo.list():
            employee = employees.get_employee(item["telegram_id"])
            result.append({
                **item,
                "employee_id": employee.id if employee else None,
                "employee_name": (employee.full_name or employee.name) if employee else None,
            })
        return result

    @router.post("/{telegram_id}/link", response_model=BotUserOut)
    async def link_bot_user(
        telegram_id: str,
        payload: BotUserLinkRequest,
        current: ResolvedUser = Depends(require_permission("access")),
    ):
        employees = EmployeeRepository()
        if employees.get_employee(telegram_id):
            raise HTTPException(status_code=400, detail="already_linked")
        old_id = payload.employee_id
        employee = employees.rekey_employee(old_id, telegram_id)
        if not employee:
            raise HTTPException(status_code=404, detail="employee_not_found")

        # Re-point all records referencing the employee's old id at the new
        # (Telegram) id, so the employee's history stays visible in their profile.
        IncentiveRepository().reassign_employee(old_id, telegram_id)
        VacationRepository().reassign_employee(old_id, telegram_id)
        AssetRepository().reassign_employee(old_id, telegram_id)
        get_shift_checkin_repository().reassign_employee(old_id, telegram_id)
        PayoutRepository().reassign_user(old_id, telegram_id)

        item = next((u for u in repo.list() if u["telegram_id"] == telegram_id), None)
        return {
            **(item or {"telegram_id": telegram_id}),
            "employee_id": employee.id,
            "employee_name": employee.full_name or employee.name,
        }

    return router

