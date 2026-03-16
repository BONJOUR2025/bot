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
        # Only allow subscribing for own employee_id
        if current.employee_id and current.employee_id != body.employee_id:
            raise HTTPException(status_code=403, detail="forbidden")
        push_service.subscribe(body.employee_id, body.subscription)
        return {"status": "subscribed"}

    @router.post("/unsubscribe")
    async def unsubscribe(
        body: UnsubscribeRequest,
        current: ResolvedUser = Depends(get_current_user),
    ) -> dict[str, str]:
        if current.employee_id and current.employee_id != body.employee_id:
            raise HTTPException(status_code=403, detail="forbidden")
        push_service.unsubscribe(body.employee_id, body.endpoint)
        return {"status": "unsubscribed"}

    @router.get("/status/{employee_id}")
    async def subscription_status(
        employee_id: str,
        current: ResolvedUser = Depends(get_current_user),
    ) -> dict[str, bool]:
        if current.employee_id and current.employee_id != employee_id:
            raise HTTPException(status_code=403, detail="forbidden")
        return {"subscribed": push_service.has_subscription(employee_id)}

    return router
