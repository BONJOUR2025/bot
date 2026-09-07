"""Логика MDM: регистрация телефонов, политика, очередь команд.

Общий контур — в docs/mdm_overview.md. Коротко: агент на телефоне сам применяет
политику и сам следит за её актуальностью, сервер только хранит желаемое
состояние и очередь команд. Поэтому здесь нет ничего, что «идёт на телефон», —
только чтение и запись состояния.
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import MDM_AGENT_APK_FILE
from app.data.mdm_repository import MdmRepository, get_mdm_repository
from app.schemas.mdm import (
    MdmAgentInfo,
    MdmAgentRolloutResult,
    MdmProvisioning,
    MdmCheckinRequest,
    MdmCommandAck,
    MdmCommandCreate,
    MdmDevice,
    MdmDeviceUpdate,
    MdmEnrollRequest,
    MdmEnrollmentInfo,
    MdmPolicy,
)
from app.settings import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_enroll_key() -> str:
    """Ключ первичной регистрации, свежим чтением из config.json.

    Тот же приём, что у счётчиков посетителей (app/api/visitor_counters.py):
    ключ, сохранённый через админку, должен начать действовать сразу, без
    перезапуска процесса.
    """
    try:
        data = json.loads(Path("config.json").read_text(encoding="utf-8"))
        if key := data.get("MDM_ENROLL_KEY"):
            return str(key)
    except Exception:
        pass
    return settings.mdm_enroll_key


def current_command_poll_seconds() -> int:
    """Интервал опроса команд, свежим чтением из config.json.

    Границы жёсткие: чаще 30 секунд телефон начнёт заметно есть батарею, реже
    часа — теряется весь смысл будильника. Мусор в конфиге не должен молча
    превращаться в неуправляемый парк.
    """
    value = settings.mdm_command_poll_seconds
    try:
        data = json.loads(Path("config.json").read_text(encoding="utf-8"))
        if (raw := data.get("MDM_COMMAND_POLL_SECONDS")) is not None:
            value = int(raw)
    except Exception:
        pass
    return max(30, min(3600, value))


def current_agent_signature_checksum() -> str:
    """Отпечаток ключа подписи, свежим чтением из config.json."""
    try:
        data = json.loads(Path("config.json").read_text(encoding="utf-8"))
        if value := data.get("MDM_AGENT_SIGNATURE_CHECKSUM"):
            return str(value)
    except Exception:
        pass
    return settings.mdm_agent_signature_checksum


def agent_apk_path() -> Path:
    return Path(MDM_AGENT_APK_FILE)


def agent_apk_url() -> str:
    """Адрес, по которому телефон качает агента.

    Публичный и без авторизации сознательно: по этой же ссылке APK тянет
    мастер первичной настройки Android при провижининге по QR — там ещё нет
    ни токена, ни возможности его ввести. Подмену ловит не доступ, а
    контрольная сумма подписи в самом QR.
    """
    return settings.public_base_url.rstrip("/") + "/api/mdm/agent.apk"


class MdmValidationError(ValueError):
    """Команда или политика не проходит проверку — наверх идёт как HTTP 400."""


class MdmService:
    def __init__(self, repo: Optional[MdmRepository] = None) -> None:
        self._repo = repo or get_mdm_repository()

    # --- агент ----------------------------------------------------------

    def enroll(self, data: MdmEnrollRequest) -> tuple[MdmDevice, str]:
        """Регистрирует телефон и выдаёт ему персональный токен.

        Повторный enroll того же device_id не создаёт дубль, а перевыпускает
        токен: это штатный путь восстановления, когда агента переустановили и
        старый токен на телефоне потерян.
        """
        existing = self._repo.get(data.device_id)
        patch: dict[str, Any] = {
            "model": data.model,
            "manufacturer": data.manufacturer,
            "android_version": data.android_version,
            "agent_version": data.agent_version,
            "device_owner": data.device_owner,
            "last_seen_at": _now(),
        }
        if not existing:
            patch.update(
                {
                    "name": None,
                    "salon_id": None,
                    "enrolled_at": _now(),
                    "policy": MdmPolicy().model_dump(),
                    "policy_version": 1,
                    "applied_policy_version": None,
                    "commands": [],
                }
            )
        self._repo.upsert(data.device_id, patch)
        token = self._repo.issue_token(data.device_id)
        return self.get_device(data.device_id), token

    def checkin(self, device: dict[str, Any], data: MdmCheckinRequest) -> MdmDevice:
        device_id = str(device.get("id"))
        for ack in data.acks:
            self._repo.ack_command(device_id, ack.command_id, ack.status, ack.result, _now())

        patch: dict[str, Any] = {
            "model": data.model or device.get("model"),
            "manufacturer": data.manufacturer or device.get("manufacturer"),
            "android_version": data.android_version or device.get("android_version"),
            "agent_version": data.agent_version or device.get("agent_version"),
            "device_owner": data.device_owner,
            "battery": data.battery,
            "applied_policy_version": data.applied_policy_version,
            "last_error": data.last_error,
            "last_seen_at": _now(),
        }
        # Координаты приходят только в ответ на команду locate, поэтому пустое
        # значение означает «не спрашивали», а не «телефон переехал в null».
        if data.latitude is not None and data.longitude is not None:
            patch["latitude"] = data.latitude
            patch["longitude"] = data.longitude
            patch["location_at"] = data.location_at or _now()

        self._repo.upsert(device_id, patch)
        return self.get_device(device_id)

    def ack_commands(self, device: dict[str, Any], acks: list[MdmCommandAck]) -> int:
        """Записывает результаты выполненных команд. Возвращает число опознанных."""
        device_id = str(device.get("id"))
        recorded = 0
        for ack in acks:
            if self._repo.ack_command(device_id, ack.command_id, ack.status, ack.result, _now()):
                recorded += 1
        return recorded

    def set_applied_version(self, device: dict[str, Any], version: int) -> None:
        """Догоняющий отчёт агента о применённой политике.

        Без него карточка на один цикл (15 минут) показывала бы «ждёт
        применения» для политики, которая на телефоне уже действует.
        """
        self._repo.upsert(str(device.get("id")), {"applied_policy_version": version})

    def take_pending_commands(self, device_id: str) -> list[dict[str, Any]]:
        return self._repo.take_pending(device_id)

    def find_by_token(self, token: str) -> Optional[dict[str, Any]]:
        return self._repo.get_by_token(token)

    # --- админка --------------------------------------------------------

    def list_devices(self) -> list[MdmDevice]:
        return [self._to_schema(d) for d in self._repo.list()]

    def get_device(self, device_id: str) -> MdmDevice:
        device = self._repo.get(device_id)
        if not device:
            raise MdmValidationError("device_not_found")
        return self._to_schema(device)

    def update_device(self, device_id: str, data: MdmDeviceUpdate) -> MdmDevice:
        if not self._repo.get(device_id):
            raise MdmValidationError("device_not_found")
        patch = {k: v for k, v in data.model_dump(exclude_unset=True).items()}
        self._repo.upsert(device_id, patch)
        return self.get_device(device_id)

    def set_policy(self, device_id: str, policy: MdmPolicy) -> MdmDevice:
        device = self._repo.get(device_id)
        if not device:
            raise MdmValidationError("device_not_found")
        if policy.kiosk.enabled and not policy.kiosk.packages:
            raise MdmValidationError("kiosk_requires_packages")

        self._repo.upsert(
            device_id,
            {
                "policy": policy.model_dump(),
                # Версия — единственное, по чему агент понимает, что политика
                # изменилась, поэтому растёт при каждом сохранении, даже если
                # содержимое совпало с предыдущим.
                "policy_version": int(device.get("policy_version") or 1) + 1,
            },
        )
        return self.get_device(device_id)

    def queue_command(self, device_id: str, data: MdmCommandCreate) -> dict[str, Any]:
        if not self._repo.get(device_id):
            raise MdmValidationError("device_not_found")

        params = dict(data.params or {})
        if data.type == "install_apk":
            url = str(params.get("url") or "").strip()
            if not url.startswith("https://"):
                # http:// пустили бы APK по открытому каналу — подменить его в
                # пути до телефона тривиально, а ставится он молча и с правами
                # владельца устройства.
                raise MdmValidationError("install_apk_requires_https_url")
            params["url"] = url
        elif data.type == "uninstall":
            package = str(params.get("package") or "").strip()
            if not package:
                raise MdmValidationError("uninstall_requires_package")
            params["package"] = package

        command = {
            "id": uuid.uuid4().hex,
            "type": data.type,
            "params": params,
            "created_at": _now(),
            "status": "pending",
            "result": None,
            "acked_at": None,
        }
        self._repo.add_command(device_id, command)
        return command

    def delete_device(self, device_id: str) -> None:
        """Убирает телефон из списка. Сам телефон при этом остаётся управляемым.

        Снять управление можно только на самом устройстве (сбросом или командой
        wipe) — удаление карточки лишь означает «мы им больше не занимаемся»,
        и агент, оставшийся на телефоне, начнёт получать 401 на чек-инах.
        """
        if not self._repo.delete(device_id):
            raise MdmValidationError("device_not_found")

    # --- провижининг по QR ----------------------------------------------

    def provisioning(self) -> MdmProvisioning:
        """Строка для QR, который читает мастер первичной настройки Android.

        Ключи с длинными именами — не наша выдумка, это протокол Android; их
        состав и написание менять нельзя. Смысловая часть три:
        откуда качать агента, чем проверить его подлинность и что передать ему
        внутрь, чтобы телефон зарегистрировался сам, без ввода руками.
        """
        problems: list[str] = []
        checksum = current_agent_signature_checksum()
        key = current_enroll_key()
        info = self.agent_info()

        if not info.available:
            problems.append("APK агента не загружен на сервер")
        if not checksum:
            problems.append("Не задан MDM_AGENT_SIGNATURE_CHECKSUM в config.json")
        if not key:
            problems.append("Не задан MDM_ENROLL_KEY в config.json")
        if problems:
            return MdmProvisioning(ready=False, problems=problems)

        payload = {
            "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME": (
                "pw.bonjour.mdm/pw.bonjour.mdm.AdminReceiver"
            ),
            "android.app.extra.PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM": checksum,
            "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION": (
                agent_apk_url()
            ),
            # Системные приложения остаются: без этого телефон приедет к
            # сотруднику без камеры, календаря и половины привычных вещей.
            "android.app.extra.PROVISIONING_LEAVE_ALL_SYSTEM_APPS_ENABLED": True,
            "android.app.extra.PROVISIONING_SKIP_ENCRYPTION": False,
            "android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE": {
                "server_url": settings.public_base_url.rstrip("/"),
                "enroll_key": key,
            },
        }
        return MdmProvisioning(ready=True, payload=json.dumps(payload, ensure_ascii=False))

    # --- APK агента -----------------------------------------------------

    def agent_info(self) -> MdmAgentInfo:
        path = agent_apk_path()
        if not path.exists():
            return MdmAgentInfo(available=False)

        raw = path.read_bytes()
        version_name, version_code = self._read_apk_version(raw)
        outdated = 0
        if version_name:
            outdated = sum(
                1
                for d in self._repo.list()
                if (d.get("agent_version") or "") != version_name
            )
        return MdmAgentInfo(
            available=True,
            version_name=version_name,
            version_code=version_code,
            size=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            uploaded_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            url=agent_apk_url(),
            outdated_devices=outdated,
        )

    def save_agent_apk(self, content: bytes) -> MdmAgentInfo:
        """Кладёт новый APK агента на сервер.

        Проверка здесь — не подпись, а вменяемость: что это вообще APK и что
        внутри наш пакет. Полноценно проверить подпись в питоне нечем, но и
        цена ошибки другая: телефон откажется ставить чужой APK поверх агента,
        потому что ключ не совпадёт. Смысл проверки — поймать «залил не тот
        файл» до того, как команда уйдёт на весь парк.
        """
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
            manifest = archive.read("AndroidManifest.xml")
        except Exception as exc:
            raise MdmValidationError("not_an_apk") from exc

        if "pw.bonjour.mdm".encode("utf-16-le") not in manifest:
            raise MdmValidationError("foreign_apk")

        agent_apk_path().write_bytes(content)
        return self.agent_info()

    def rollout_agent_update(self) -> MdmAgentRolloutResult:
        """Ставит команду обновления телефонам, чья версия отличается от лежащей.

        Сравнение по имени версии, а не «новее/старее»: откат на предыдущую
        версию — такой же законный сценарий, как обновление, и запрещать его
        сравнением номеров незачем.
        """
        info = self.agent_info()
        if not info.available:
            raise MdmValidationError("agent_apk_not_uploaded")
        if not info.version_name:
            # Версии нет — значит APK собран до того, как её начали класть
            # внутрь. Рассылать вслепую нельзя: обновим все телефоны в цикле.
            raise MdmValidationError("agent_apk_version_unknown")

        queued = skipped = 0
        for device in self._repo.list():
            if (device.get("agent_version") or "") == info.version_name:
                skipped += 1
                continue
            self.queue_command(
                str(device.get("id")),
                MdmCommandCreate(type="install_apk", params={"url": info.url}),
            )
            queued += 1
        return MdmAgentRolloutResult(queued=queued, skipped=skipped)

    @staticmethod
    def _read_apk_version(content: bytes) -> tuple[Optional[str], Optional[int]]:
        """Версия лежит в assets/agent_version.json, который кладёт сборка.

        Разбирать бинарный манифест Android ради двух чисел — несоразмерно, а
        имя файла по дороге может стать каким угодно.
        """
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
            data = json.loads(archive.read("assets/agent_version.json").decode("utf-8"))
            return str(data["version_name"]), int(data["version_code"])
        except Exception:
            return None, None

    def enrollment_info(self) -> MdmEnrollmentInfo:
        key = current_enroll_key()
        return MdmEnrollmentInfo(
            server_url=settings.public_base_url,
            enroll_key=key,
            configured=bool(key),
            command_poll_seconds=current_command_poll_seconds(),
        )

    # --- вспомогательное ------------------------------------------------

    @staticmethod
    def _to_schema(device: dict[str, Any]) -> MdmDevice:
        data = {k: v for k, v in device.items() if k != "token"}
        data.setdefault("policy", MdmPolicy().model_dump())
        return MdmDevice.model_validate(data)


_service: Optional[MdmService] = None


def get_mdm_service() -> MdmService:
    global _service
    if _service is None:
        _service = MdmService()
    return _service
