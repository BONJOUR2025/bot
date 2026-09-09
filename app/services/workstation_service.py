"""Логика наблюдения за салонными компьютерами.

Агент только отчитывается — здесь нет ничего, что «идёт на компьютер».
Сервис принимает отчёты, хранит состояние и умеет сказать, что с машиной не так.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.data.workstation_repository import WorkstationRepository, get_workstation_repository
from app.schemas.workstation import (
    Workstation,
    WorkstationCheckin,
    WorkstationEnrollRequest,
    WorkstationUpdate,
)
from app.settings import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_enroll_key() -> str:
    """Ключ регистрации, свежим чтением из config.json — как у MDM и счётчиков:
    заданный через админку ключ должен действовать сразу, без перезапуска."""
    try:
        data = json.loads(Path("config.json").read_text(encoding="utf-8"))
        if key := data.get("WORKSTATION_ENROLL_KEY"):
            return str(key)
    except Exception:
        pass
    return settings.workstation_enroll_key


def current_checkin_seconds() -> int:
    value = settings.workstation_checkin_seconds
    try:
        data = json.loads(Path("config.json").read_text(encoding="utf-8"))
        if (raw := data.get("WORKSTATION_CHECKIN_SECONDS")) is not None:
            value = int(raw)
    except Exception:
        pass
    # Чаще минуты незачем: показатели меняются медленно, а отчёты копятся.
    # Реже часа — теряется смысл наблюдения.
    return max(60, min(3600, value))


def current_watch_processes() -> list[str]:
    """Процессы, о которых агент должен доложить.

    Список задаёт сервер, а не агент: добавить наблюдение за новой программой
    нужно уметь без обхода машин, а обновлять агент на кассовых ПК дорого.
    """
    try:
        data = json.loads(Path("config.json").read_text(encoding="utf-8"))
        raw = data.get("WORKSTATION_WATCH_PROCESSES")
        if isinstance(raw, list) and raw:
            return [str(x) for x in raw if str(x).strip()]
    except Exception:
        pass
    return ["fbserver.exe", "fb_inet_server.exe", "Agbis.exe"]


# Пороги тревог. Место на диске — главный: при переполнении встаёт Firebird,
# а с ним продажи салона.
LOW_DISK_PERCENT = 10.0
LOW_DISK_GB = 5.0


class WorkstationValidationError(ValueError):
    pass


class WorkstationService:
    def __init__(self, repo: Optional[WorkstationRepository] = None) -> None:
        self._repo = repo or get_workstation_repository()

    # --- агент ----------------------------------------------------------

    def enroll(self, data: WorkstationEnrollRequest) -> tuple[str, str]:
        """Регистрация по имени машины: повторный запуск агента на том же ПК
        не плодит карточки, а обновляет токен."""
        hostname = data.hostname.strip()
        existing = next(
            (w for w in self._repo.list() if str(w.get("hostname") or "").lower() == hostname.lower()),
            None,
        )
        workstation_id = str(existing["id"]) if existing else secrets.token_hex(8)
        token = secrets.token_urlsafe(32)
        self._repo.upsert(workstation_id, {
            "hostname": hostname,
            "token": token,
            "agent_version": data.agent_version,
            "enrolled_at": _now(),
        })
        return workstation_id, token

    def find_by_token(self, token: str) -> Optional[dict[str, Any]]:
        return self._repo.get_by_token(token or "")

    def checkin(self, workstation: dict[str, Any], data: WorkstationCheckin) -> Workstation:
        patch: dict[str, Any] = {"last_seen_at": _now()}
        # Пишем только то, что реально пришло: сбор отдельного показателя мог
        # не удаться, и это не повод затирать прежнее значение пустотой.
        for field in (
            "hostname", "os_version", "agent_version", "uptime_seconds",
            "cpu_percent", "ram_total_mb", "ram_used_percent", "ip_address",
            "pending_reboot",
        ):
            value = getattr(data, field)
            if value is not None:
                patch[field] = value
        if data.disks:
            patch["disks"] = [d.model_dump() for d in data.disks]
        if data.processes:
            patch["processes"] = data.processes
        patch["last_error"] = data.last_error
        updated = self._repo.upsert(str(workstation.get("id")), patch)
        return self._to_schema(updated)

    # --- панель ---------------------------------------------------------

    def list_workstations(self) -> list[Workstation]:
        return [self._to_schema(w) for w in self._repo.list()]

    def get(self, workstation_id: str) -> Workstation:
        w = self._repo.get(workstation_id)
        if not w:
            raise WorkstationValidationError("workstation_not_found")
        return self._to_schema(w)

    def update(self, workstation_id: str, data: WorkstationUpdate) -> Workstation:
        if not self._repo.get(workstation_id):
            raise WorkstationValidationError("workstation_not_found")
        patch = {k: v for k, v in data.model_dump().items() if v is not None}
        return self._to_schema(self._repo.upsert(workstation_id, patch))

    def delete(self, workstation_id: str) -> None:
        if not self._repo.delete(workstation_id):
            raise WorkstationValidationError("workstation_not_found")

    # --- здоровье -------------------------------------------------------

    @staticmethod
    def problems(workstation: dict[str, Any]) -> list[str]:
        """Что не так с машиной. Пустой список — всё в порядке.

        Отдельно от «молчит»: молчание считает сторож по last_seen_at, а здесь
        только то, о чём компьютер сам рассказал.
        """
        found: list[str] = []

        for disk in workstation.get("disks") or []:
            try:
                free_gb = float(disk.get("free_gb"))
                percent = float(disk.get("free_percent"))
            except (TypeError, ValueError):
                continue
            if percent < LOW_DISK_PERCENT or free_gb < LOW_DISK_GB:
                found.append(f"мало места на {disk.get('mount')} ({free_gb:.1f} ГБ, {percent:.0f}%)")

        for name, running in (workstation.get("processes") or {}).items():
            if running is False:
                found.append(f"не запущен {name}")

        if workstation.get("pending_reboot") is True:
            found.append("ждёт перезагрузки после обновлений")

        if error := workstation.get("last_error"):
            found.append(f"агент сообщает об ошибке: {error}")

        return found

    # --- вспомогательное ------------------------------------------------

    @staticmethod
    def _to_schema(workstation: dict[str, Any]) -> Workstation:
        return Workstation.model_validate({k: v for k, v in workstation.items() if k != "token"})


_service: Optional[WorkstationService] = None


def get_workstation_service() -> WorkstationService:
    global _service
    if _service is None:
        _service = WorkstationService()
    return _service
