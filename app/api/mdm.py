"""API управления корпоративными Android-телефонами салонов.

Два роутера с разной авторизацией, как у счётчиков посетителей:
устройства не могут держать пользовательскую сессию, поэтому агент ходит по
статическому ключу регистрации и персональному токену, а админские ручки — по
обычному праву доступа `mdm`.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.dependencies import require_permission
from app.schemas.mdm import (
    MdmAckRequest,
    MdmCheckinRequest,
    MdmCheckinResponse,
    MdmCommand,
    MdmCommandCreate,
    MdmDevice,
    MdmDeviceUpdate,
    MdmEnrollRequest,
    MdmEnrollResponse,
    MdmEnrollmentInfo,
    MdmPolicy,
)
from app.services.mdm_service import (
    MdmService,
    MdmValidationError,
    current_enroll_key,
    get_mdm_service,
)

# Как часто агент выходит на связь. 15 минут — минимальный период, который
# WorkManager на Android гарантирует; просить чаще бессмысленно, система всё
# равно урежет.
CHECKIN_INTERVAL_MINUTES = 15


def create_mdm_device_router(service: MdmService) -> APIRouter:
    """Роутер для агентов на телефонах. Без пользовательской сессии."""

    router = APIRouter(prefix="/mdm/device", tags=["MDM"])

    def _check_enroll_key(x_enroll_key: Optional[str] = Header(default=None, alias="X-Enroll-Key")) -> None:
        expected = current_enroll_key()
        if not expected:
            raise HTTPException(status_code=503, detail="enrollment_not_configured")
        if not x_enroll_key or not secrets.compare_digest(expected, x_enroll_key):
            raise HTTPException(status_code=401, detail="invalid_enroll_key")

    def _authenticated_device(
        x_device_token: Optional[str] = Header(default=None, alias="X-Device-Token"),
    ) -> dict[str, Any]:
        device = service.find_by_token(x_device_token or "")
        if not device:
            raise HTTPException(status_code=401, detail="invalid_device_token")
        return device

    @router.post("/enroll", response_model=MdmEnrollResponse)
    async def enroll_device(
        data: MdmEnrollRequest,
        _: None = Depends(_check_enroll_key),
    ) -> MdmEnrollResponse:
        device, token = service.enroll(data)
        return MdmEnrollResponse(
            device_id=device.id,
            token=token,
            policy_version=device.policy_version,
            policy=device.policy,
        )

    @router.post("/checkin", response_model=MdmCheckinResponse)
    async def checkin_device(
        data: MdmCheckinRequest,
        device: dict[str, Any] = Depends(_authenticated_device),
    ) -> MdmCheckinResponse:
        updated = service.checkin(device, data)
        pending = service.take_pending_commands(updated.id)
        return MdmCheckinResponse(
            policy_version=updated.policy_version,
            policy=updated.policy,
            commands=[MdmCommand.model_validate(c) for c in pending],
            checkin_interval_minutes=CHECKIN_INTERVAL_MINUTES,
        )

    @router.post("/ack")
    async def ack_commands(
        data: MdmAckRequest,
        device: dict[str, Any] = Depends(_authenticated_device),
    ) -> dict[str, int]:
        recorded = service.ack_commands(device, data.acks)
        if data.applied_policy_version is not None:
            service.set_applied_version(device, data.applied_policy_version)
        return {"recorded": recorded}

    return router


def create_mdm_router(service: MdmService) -> APIRouter:
    """Админские ручки: список телефонов, политика, команды."""

    router = APIRouter(prefix="/mdm", tags=["MDM"])

    def _handle(exc: MdmValidationError) -> HTTPException:
        detail = str(exc)
        status = 404 if detail == "device_not_found" else 400
        return HTTPException(status_code=status, detail=detail)

    @router.get("/enrollment", response_model=MdmEnrollmentInfo)
    async def get_enrollment_info(
        current=Depends(require_permission("mdm")),
    ) -> MdmEnrollmentInfo:
        return service.enrollment_info()

    @router.get("/devices", response_model=list[MdmDevice])
    async def list_devices(current=Depends(require_permission("mdm"))) -> list[MdmDevice]:
        return service.list_devices()

    @router.get("/devices/{device_id}", response_model=MdmDevice)
    async def get_device(
        device_id: str,
        current=Depends(require_permission("mdm")),
    ) -> MdmDevice:
        try:
            return service.get_device(device_id)
        except MdmValidationError as exc:
            raise _handle(exc)

    @router.patch("/devices/{device_id}", response_model=MdmDevice)
    async def update_device(
        device_id: str,
        data: MdmDeviceUpdate,
        current=Depends(require_permission("mdm")),
    ) -> MdmDevice:
        try:
            return service.update_device(device_id, data)
        except MdmValidationError as exc:
            raise _handle(exc)

    @router.put("/devices/{device_id}/policy", response_model=MdmDevice)
    async def set_device_policy(
        device_id: str,
        policy: MdmPolicy,
        current=Depends(require_permission("mdm")),
    ) -> MdmDevice:
        try:
            return service.set_policy(device_id, policy)
        except MdmValidationError as exc:
            raise _handle(exc)

    @router.post("/devices/{device_id}/commands", response_model=MdmCommand, status_code=201)
    async def queue_command(
        device_id: str,
        data: MdmCommandCreate,
        current=Depends(require_permission("mdm")),
    ) -> MdmCommand:
        try:
            return MdmCommand.model_validate(service.queue_command(device_id, data))
        except MdmValidationError as exc:
            raise _handle(exc)

    @router.delete("/devices/{device_id}")
    async def delete_device(
        device_id: str,
        current=Depends(require_permission("mdm")),
    ) -> dict[str, str]:
        try:
            service.delete_device(device_id)
        except MdmValidationError as exc:
            raise _handle(exc)
        return {"status": "ok"}

    return router
