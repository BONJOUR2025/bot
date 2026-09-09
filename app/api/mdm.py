"""API управления корпоративными Android-телефонами салонов.

Два роутера с разной авторизацией, как у счётчиков посетителей:
устройства не могут держать пользовательскую сессию, поэтому агент ходит по
статическому ключу регистрации и персональному токену, а админские ручки — по
обычному праву доступа `mdm`.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.api.dependencies import require_permission
from app.schemas.mdm import (
    MdmAckRequest,
    MdmSettingsUpdate,
    MdmAgentInfo,
    MdmAgentRolloutResult,
    MdmBroadcastResult,
    MdmLibraryApp,
    MdmProvisioning,
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
    agent_apk_path,
    current_upload_token,
    current_command_poll_seconds,
    current_enroll_key,
    get_mdm_service,
)

# Как часто агент выходит на связь. 15 минут — минимальный период, который
# WorkManager на Android гарантирует; просить чаще бессмысленно, система всё
# равно урежет.
CHECKIN_INTERVAL_MINUTES = 15

# Как часто агент отдельно опрашивает очередь команд, задаётся ключом
# MDM_COMMAND_POLL_SECONDS в config.json (см. current_command_poll_seconds).
# Полный чек-ин раз в 15 минут — потолок WorkManager, для «заблокируй
# телефон» это слишком долго, поэтому очередь агент забирает будильником.


def _apk_response(path, filename: str) -> FileResponse:
    """Отдаёт APK так, чтобы его не испортило сжатие.

    В приложении включён GZipMiddleware, и он честно жал APK всем, кто прислал
    Accept-Encoding: gzip, — включая мастер первичной настройки Android. Тот
    сохраняет полученное в файл и сверяет подпись, а у сжатого файла она,
    естественно, не сходится: провижининг по QR падал с «Can't set up device».
    Заголовок Content-Encoding заставляет middleware пропустить ответ мимо себя.

    Сжимать APK и незачем: это zip, выигрыш около девяти процентов, а цена —
    потеря Content-Length и вот такие поломки у неразборчивых клиентов.
    """
    return FileResponse(
        path,
        media_type="application/vnd.android.package-archive",
        filename=filename,
        headers={"Content-Encoding": "identity"},
    )


def create_mdm_public_router() -> APIRouter:
    """Раздача APK агента. Без авторизации — иначе не сработает провижининг.

    По этой ссылке APK тянет мастер первичной настройки Android, когда на
    телефоне ещё нет ничего. Подмену ловит не доступ, а контрольная сумма
    подписи, зашитая в QR: файл с чужим ключом телефон просто не поставит.
    """

    router = APIRouter(prefix="/mdm", tags=["MDM"])

    @router.get("/agent.apk")
    async def download_agent_apk() -> FileResponse:
        path = agent_apk_path()
        if not path.exists():
            raise HTTPException(status_code=404, detail="agent_apk_not_uploaded")
        return _apk_response(path, "bonjour-mdm-agent.apk")

    @router.post("/agent/upload", response_model=MdmAgentInfo)
    async def upload_agent_from_ci(
        file: UploadFile = File(...),
        x_upload_token: Optional[str] = Header(default=None, alias="X-Upload-Token"),
    ) -> MdmAgentInfo:
        """Сборка кладёт свежий APK агента сама.

        Отдельная авторизация по токену, а не по сессии: у сборки её быть не
        может. Это последнее звено, из-за которого обновление парка требовало
        человека с браузером — теперь собралось и сразу лежит на сервере.
        """
        expected = current_upload_token()
        if not expected:
            raise HTTPException(status_code=503, detail="upload_not_configured")
        if not x_upload_token or not secrets.compare_digest(expected, x_upload_token):
            raise HTTPException(status_code=401, detail="invalid_upload_token")
        try:
            return get_mdm_service().save_agent_apk(await file.read())
        except MdmValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.get("/devices/{device_id}/snapshots/{snapshot_id}.jpg")
    async def get_snapshot(device_id: str, snapshot_id: str, exp: int = 0, sig: str = "") -> FileResponse:
        # Подписанная ссылка вместо сессии: снимок открывается в браузере
        # обычным <a href>, как скан паспорта, но подпись не даёт достать его
        # чужому. См. sign_snapshot/verify_snapshot_sig.
        from app.services.mdm_service import verify_snapshot_sig

        if not verify_snapshot_sig(device_id, snapshot_id, exp, sig):
            raise HTTPException(status_code=403, detail="invalid_or_expired_signature")
        try:
            path = get_mdm_service().snapshot_path(device_id, snapshot_id)
        except MdmValidationError:
            raise HTTPException(status_code=404, detail="snapshot_not_found")
        return FileResponse(path, media_type="image/jpeg")

    @router.get("/apps/{app_id}.apk")
    async def download_library_app(app_id: str) -> FileResponse:
        try:
            path = get_mdm_service().library_app_path(app_id)
        except MdmValidationError:
            raise HTTPException(status_code=404, detail="app_not_found")
        return _apk_response(path, app_id + ".apk")

    return router


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
            command_poll_seconds=current_command_poll_seconds(),
        )

    @router.post("/snapshot")
    async def upload_snapshot(
        file: UploadFile = File(...),
        lens: Optional[str] = Header(default=None, alias="X-Lens"),
        device: dict[str, Any] = Depends(_authenticated_device),
    ) -> dict[str, str]:
        snapshot_id = service.save_snapshot(device, lens, await file.read())
        return {"status": "ok", "snapshot_id": snapshot_id}

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

    @router.put("/settings", response_model=MdmEnrollmentInfo)
    async def update_settings(
        data: MdmSettingsUpdate,
        current=Depends(require_permission("mdm")),
    ) -> MdmEnrollmentInfo:
        try:
            return service.set_command_poll_seconds(data.command_poll_seconds)
        except MdmValidationError as exc:
            raise _handle(exc)

    @router.get("/apps", response_model=list[MdmLibraryApp])
    async def list_library(
        current=Depends(require_permission("mdm")),
    ) -> list[MdmLibraryApp]:
        return service.list_library()

    @router.post("/apps", response_model=MdmLibraryApp)
    async def upload_library_app(
        file: UploadFile = File(...),
        current=Depends(require_permission("mdm")),
    ) -> MdmLibraryApp:
        try:
            return service.save_library_app(file.filename or "app.apk", await file.read())
        except MdmValidationError as exc:
            raise _handle(exc)

    @router.delete("/apps/{app_id}")
    async def delete_library_app(
        app_id: str,
        current=Depends(require_permission("mdm")),
    ) -> dict[str, str]:
        try:
            service.delete_library_app(app_id)
        except MdmValidationError as exc:
            raise _handle(exc)
        return {"status": "ok"}

    @router.post("/devices/{device_id}/install/{app_id}", response_model=MdmCommand, status_code=201)
    async def install_library_app(
        device_id: str,
        app_id: str,
        current=Depends(require_permission("mdm")),
    ) -> MdmCommand:
        try:
            return MdmCommand.model_validate(service.install_library_app(device_id, app_id))
        except MdmValidationError as exc:
            raise _handle(exc)

    @router.get("/provisioning", response_model=MdmProvisioning)
    async def get_provisioning(
        current=Depends(require_permission("mdm")),
    ) -> MdmProvisioning:
        return service.provisioning()

    @router.get("/agent", response_model=MdmAgentInfo)
    async def get_agent_info(
        current=Depends(require_permission("mdm")),
    ) -> MdmAgentInfo:
        return service.agent_info()

    @router.post("/agent", response_model=MdmAgentInfo)
    async def upload_agent_apk(
        file: UploadFile = File(...),
        current=Depends(require_permission("mdm")),
    ) -> MdmAgentInfo:
        try:
            return service.save_agent_apk(await file.read())
        except MdmValidationError as exc:
            raise _handle(exc)

    @router.post("/agent/rollout", response_model=MdmAgentRolloutResult)
    async def rollout_agent(
        current=Depends(require_permission("mdm")),
    ) -> MdmAgentRolloutResult:
        try:
            return service.rollout_agent_update()
        except MdmValidationError as exc:
            raise _handle(exc)

    @router.post("/broadcast", response_model=MdmBroadcastResult)
    async def broadcast(
        data: MdmCommandCreate,
        salon_id: Optional[str] = None,
        current=Depends(require_permission("mdm")),
    ) -> MdmBroadcastResult:
        """Одна команда сразу всем телефонам (или всем в салоне ?salon_id=...)."""
        try:
            return service.broadcast_command(data, salon_id)
        except MdmValidationError as exc:
            raise _handle(exc)

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
