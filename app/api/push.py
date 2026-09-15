from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.access_control_service import ResolvedUser
from app.services.push_service import PushService

from .dependencies import get_current_user


class SubscribeRequest(BaseModel):
    subscription: dict[str, Any]
    employee_id: str


class UnsubscribeRequest(BaseModel):
    endpoint: str
    employee_id: str


def create_push_router(push_service: PushService) -> APIRouter:
    router = APIRouter(prefix="/push", tags=["Push"])

    def _ensure_own(current: ResolvedUser, employee_id: str) -> None:
        # Сотрудник подписывает только себя. Аккаунт без сотрудника раньше
        # проходил проверку для любого id и мог получать чужие уведомления
        # (статусы выплат) — теперь только с правом раздела «Сотрудники».
        if current.employee_id:
            if current.employee_id != employee_id:
                raise HTTPException(status_code=403, detail="forbidden")
            return
        if "*" not in current.permissions and "employees" not in current.permissions:
            raise HTTPException(status_code=403, detail="forbidden")

    @router.get("/vapid-public-key")
    async def vapid_public_key(
        _: ResolvedUser = Depends(get_current_user),
    ) -> dict[str, str]:
        return {"key": push_service.public_key_b64()}

    @router.post("/subscribe")
    async def subscribe(
        body: SubscribeRequest,
        current: ResolvedUser = Depends(get_current_user),
    ) -> dict[str, str]:
        _ensure_own(current, body.employee_id)
        push_service.subscribe(body.employee_id, body.subscription)
        return {"status": "subscribed"}

    @router.post("/unsubscribe")
    async def unsubscribe(
        body: UnsubscribeRequest,
        current: ResolvedUser = Depends(get_current_user),
    ) -> dict[str, str]:
        _ensure_own(current, body.employee_id)
        push_service.unsubscribe(body.employee_id, body.endpoint)
        return {"status": "unsubscribed"}

    @router.get("/status/{employee_id}")
    async def subscription_status(
        employee_id: str,
        current: ResolvedUser = Depends(get_current_user),
    ) -> dict[str, bool]:
        _ensure_own(current, employee_id)
        return {"subscribed": push_service.has_subscription(employee_id)}

    return router
