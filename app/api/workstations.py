"""API управления салонными компьютерами.

Два роутера с разной авторизацией, как у MDM: агент не может держать
пользовательскую сессию и ходит по ключу регистрации и персональному токену,
админские ручки — по обычному праву доступа.

Ручки «выполнить произвольную строку» здесь нет намеренно — см.
app/schemas/workstation.py.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException

from app.api.dependencies import require_permission
from app.schemas.workstation import (
    Workstation,
    WorkstationCheckin,
    WorkstationCheckinResponse,
    WorkstationCommand,
    WorkstationCommandCreate,
    WorkstationEnrollRequest,
    WorkstationEnrollResponse,
    WorkstationPollRequest,
    WorkstationPollResponse,
    WorkstationUpdate,
)
from app.services.workstation_service import (
    WorkstationService,
    WorkstationValidationError,
    current_allowed_apps,
    current_checkin_seconds,
    current_enroll_key,
    current_hold_seconds,
    current_watch_processes,
)

# Такт ожидания в длинном опросе: отклик упирается в полсекунды, а сторожевая
# проверка очереди целиком делается раз в POLL_SAFETY_TICKS тактов — на случай
# правки файла, не заметной по времени и размеру.
POLL_TICK_SECONDS = 0.5
POLL_SAFETY_TICKS = 10


def create_workstation_agent_router(service: WorkstationService) -> APIRouter:
    router = APIRouter(prefix="/workstations/agent", tags=["Workstations"])

    def _check_enroll_key(
        x_enroll_key: Optional[str] = Header(default=None, alias="X-Enroll-Key"),
    ) -> None:
        expected = current_enroll_key()
        if not expected:
            raise HTTPException(status_code=503, detail="enrollment_not_configured")
        if not x_enroll_key or not secrets.compare_digest(expected, x_enroll_key):
            raise HTTPException(status_code=401, detail="invalid_enroll_key")

    def _authenticated(
        x_workstation_token: Optional[str] = Header(default=None, alias="X-Workstation-Token"),
    ) -> dict[str, Any]:
        found = service.find_by_token(x_workstation_token or "")
        if not found:
            raise HTTPException(status_code=401, detail="invalid_token")
        return found

    @router.post("/enroll", response_model=WorkstationEnrollResponse)
    async def enroll(
        data: WorkstationEnrollRequest,
        _: None = Depends(_check_enroll_key),
    ) -> WorkstationEnrollResponse:
        workstation_id, token = service.enroll(data)
        return WorkstationEnrollResponse(workstation_id=workstation_id, token=token)

    @router.post("/checkin", response_model=WorkstationCheckinResponse)
    async def checkin(
        data: WorkstationCheckin,
        workstation: dict[str, Any] = Depends(_authenticated),
    ) -> WorkstationCheckinResponse:
        service.checkin(workstation, data)
        return WorkstationCheckinResponse(
            interval_seconds=current_checkin_seconds(),
            watch_processes=current_watch_processes(),
            allowed_apps=sorted(current_allowed_apps()),
        )

    @router.post("/poll", response_model=WorkstationPollResponse)
    async def poll(
        data: WorkstationPollRequest = Body(default=WorkstationPollRequest()),
        workstation: dict[str, Any] = Depends(_authenticated),
    ) -> WorkstationPollResponse:
        """Длинный опрос: держим запрос, пока не появится команда.

        Тот же приём, что у телефонов: компьютер висит на одном открытом
        запросе, и команда уходит в него в момент постановки — отсюда отклик в
        секунды вместо интервала отчёта.
        """
        workstation_id = str(workstation.get("id"))
        if data.acks:
            service.ack_commands(workstation, data.acks)
        # Машина на связи — значит, всё, что она забрала давно и не
        # подтвердила, она уже не подтвердит.
        service.expire_stale_commands(workstation_id)

        hold = current_hold_seconds()
        deadline = time.monotonic() + hold
        marker = service.queue_marker()
        commands = service.take_pending_commands(workstation_id)
        tick = 0
        while not commands and time.monotonic() < deadline:
            await asyncio.sleep(POLL_TICK_SECONDS)
            tick += 1
            current = service.queue_marker()
            if current == marker and tick % POLL_SAFETY_TICKS:
                continue
            marker = current
            commands = service.take_pending_commands(workstation_id)

        return WorkstationPollResponse(
            commands=[WorkstationCommand.model_validate(c) for c in commands],
            hold_seconds=hold,
            allowed_apps=sorted(current_allowed_apps()),
        )

    return router


def create_workstation_router(service: WorkstationService) -> APIRouter:
    router = APIRouter(prefix="/workstations", tags=["Workstations"])

    def _handle(exc: WorkstationValidationError) -> HTTPException:
        detail = str(exc)
        status = 404 if detail == "workstation_not_found" else 400
        return HTTPException(status_code=status, detail=detail)

    @router.get("", response_model=list[Workstation])
    async def list_workstations(current=Depends(require_permission("mdm"))) -> list[Workstation]:
        return service.list_workstations()

    @router.get("/allowed-apps", response_model=list[str])
    async def allowed_apps(current=Depends(require_permission("mdm"))) -> list[str]:
        """Что разрешено запускать. Панель строит по этому списку кнопки —
        оператор не должен угадывать имя программы и получать отказ."""
        return sorted(current_allowed_apps())

    @router.post("/{workstation_id}/commands", response_model=WorkstationCommand, status_code=201)
    async def queue_command(
        workstation_id: str,
        data: WorkstationCommandCreate,
        current=Depends(require_permission("mdm")),
    ) -> WorkstationCommand:
        try:
            return WorkstationCommand.model_validate(service.queue_command(workstation_id, data))
        except WorkstationValidationError as exc:
            raise _handle(exc)

    @router.delete("/{workstation_id}/commands/{command_id}", response_model=Workstation)
    async def cancel_command(
        workstation_id: str,
        command_id: str,
        current=Depends(require_permission("mdm")),
    ) -> Workstation:
        try:
            return service.cancel_command(workstation_id, command_id)
        except WorkstationValidationError as exc:
            raise _handle(exc)

    @router.patch("/{workstation_id}", response_model=Workstation)
    async def update(
        workstation_id: str,
        data: WorkstationUpdate,
        current=Depends(require_permission("mdm")),
    ) -> Workstation:
        try:
            return service.update(workstation_id, data)
        except WorkstationValidationError as exc:
            raise _handle(exc)

    @router.delete("/{workstation_id}")
    async def delete(
        workstation_id: str,
        current=Depends(require_permission("mdm")),
    ) -> dict[str, str]:
        try:
            service.delete(workstation_id)
        except WorkstationValidationError as exc:
            raise _handle(exc)
        return {"status": "ok"}

    return router
