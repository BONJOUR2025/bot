"""API наблюдения за салонными компьютерами.

Два роутера с разной авторизацией, как у MDM: агент не может держать
пользовательскую сессию и ходит по ключу регистрации и персональному токену,
админские ручки — по обычному праву доступа.

Ручек, что-либо делающих НА компьютере, здесь нет и быть не должно: агент
только отчитывается. См. app/schemas/workstation.py.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.dependencies import require_permission
from app.schemas.workstation import (
    Workstation,
    WorkstationCheckin,
    WorkstationCheckinResponse,
    WorkstationEnrollRequest,
    WorkstationEnrollResponse,
    WorkstationUpdate,
)
from app.services.workstation_service import (
    WorkstationService,
    WorkstationValidationError,
    current_checkin_seconds,
    current_enroll_key,
    current_watch_processes,
)


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
        )

    return router


def create_workstation_router(service: WorkstationService) -> APIRouter:
    router = APIRouter(prefix="/workstations", tags=["Workstations"])

    def _handle(exc: WorkstationValidationError) -> HTTPException:
        detail = str(exc)
        return HTTPException(status_code=404 if detail == "workstation_not_found" else 400, detail=detail)

    @router.get("", response_model=list[Workstation])
    async def list_workstations(current=Depends(require_permission("mdm"))) -> list[Workstation]:
        return service.list_workstations()

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
