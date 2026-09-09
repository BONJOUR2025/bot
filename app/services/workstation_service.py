"""Логика управления салонными компьютерами.

Принимает отчёты агентов, хранит состояние, ставит команды в очередь и умеет
сказать, что с машиной не так.

Команды «выполнить произвольную строку» здесь нет намеренно: на этих машинах
касса и Firebird с продажами. Запускать и перезапускать можно только программы
из белого списка на сервере (WORKSTATION_ALLOWED_APPS) — имя программы не
свободный параметр команды, а ссылка на этот список.
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.data.workstation_repository import WorkstationRepository, get_workstation_repository
from app.schemas.workstation import (
    Workstation,
    WorkstationCheckin,
    WorkstationCommandAck,
    WorkstationCommandCreate,
    WorkstationEnrollRequest,
    WorkstationUpdate,
)
from app.settings import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_fresh(timestamp: Optional[str], max_age_seconds: int) -> bool:
    """Не старше ли отметка заданного возраста. Нечитаемая — считается старой."""
    if not timestamp:
        return False
    try:
        moment = datetime.fromisoformat(str(timestamp))
    except ValueError:
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - moment).total_seconds() < max_age_seconds


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


def current_allowed_apps() -> list[str]:
    """Имена программ, которые разрешено запускать и перезапускать.

    Здесь только ИМЕНА — пути к исполняемым файлам лежат в agent.ini на самой
    машине. Это не лишний слой: если бы путь приходил с сервера, захваченный
    сервер указал бы любой файл и run_app стал бы «выполнить что угодно» на
    кассовом компьютере. Так сервер может лишь сослаться на то, что машина уже
    разрешила у себя.

    Пустой список по умолчанию — правильное поведение: пока оператор не
    перечислил программы явно, запускать нечего.
    """
    try:
        data = json.loads(Path("config.json").read_text(encoding="utf-8"))
        raw = data.get("WORKSTATION_ALLOWED_APPS")
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
    except Exception:
        pass
    return []


def current_hold_seconds() -> int:
    """Сколько держать длинный опрос команд. Границы те же, что у телефонов:
    короче пяти секунд — это уже обычный опрос, дольше пятидесяти — соединение
    успевает порваться в туннеле."""
    try:
        data = json.loads(Path("config.json").read_text(encoding="utf-8"))
        if (raw := data.get("WORKSTATION_HOLD_SECONDS")) is not None:
            return max(5, min(50, int(raw)))
    except Exception:
        pass
    return 25


# Сколько ждать подтверждения, прежде чем считать команду потерянной. Процесс
# агента могли убить между исполнением и отчётом, и вечное «на компьютере» в
# панели врёт хуже, чем признание через четверть часа.
STALE_COMMAND_SECONDS = 15 * 60

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
        for field in ("user_session", "logged_user"):
            value = getattr(data, field)
            if value is not None:
                patch[field] = value
        patch["last_error"] = data.last_error
        updated = self._repo.upsert(str(workstation.get("id")), patch)
        if data.acks:
            self.ack_commands(workstation, data.acks)
        return self._to_schema(updated)

    # --- команды ---------------------------------------------------------

    def queue_command(self, workstation_id: str, data: WorkstationCommandCreate) -> dict[str, Any]:
        if not self._repo.get(workstation_id):
            raise WorkstationValidationError("workstation_not_found")

        params = dict(data.params or {})
        if data.type in ("reboot", "shutdown"):
            # Даём человеку за кассой время закрыть смену: мгновенное
            # выключение посреди рабочего дня стоит дороже минуты ожидания.
            delay = int(params.get("delay_seconds") or 60)
            params["delay_seconds"] = max(0, min(3600, delay))
        elif data.type == "message":
            text = str(params.get("text") or "").strip()
            if not text:
                raise WorkstationValidationError("message_requires_text")
            params["text"] = text[:600]
            params["title"] = str(params.get("title") or "").strip()[:120]
        elif data.type in ("restart_process", "run_app"):
            app = str(params.get("app") or "").strip()
            if not app:
                raise WorkstationValidationError(data.type + "_requires_app")
            allowed = current_allowed_apps()
            if app not in allowed:
                # Не свободный параметр, а ссылка на белый список сервера.
                raise WorkstationValidationError("app_not_allowed")
            params["app"] = app

        command = {
            "id": uuid.uuid4().hex,
            "type": data.type,
            "params": params,
            "created_at": _now(),
            "status": "pending",
            "result": None,
            "acked_at": None,
        }
        self._repo.add_command(workstation_id, command)
        return command

    def take_pending_commands(self, workstation_id: str) -> list[dict[str, Any]]:
        return self._repo.take_pending(workstation_id)

    def ack_commands(self, workstation: dict[str, Any], acks: list[WorkstationCommandAck]) -> int:
        recorded = 0
        for ack in acks:
            if self._repo.ack_command(
                str(workstation.get("id")), ack.command_id, ack.status, ack.result, _now()
            ):
                recorded += 1
        return recorded

    def cancel_command(self, workstation_id: str, command_id: str) -> Workstation:
        """Снять команду, пока она не ушла на машину.

        С длинным опросом запас времени — секунды, но именно в них и надо
        успеть, если перезагрузку отправили не на тот компьютер.
        """
        if not self._repo.get(workstation_id):
            raise WorkstationValidationError("workstation_not_found")
        if not self._repo.cancel_command(workstation_id, command_id):
            raise WorkstationValidationError("command_not_cancelable")
        return self.get(workstation_id)

    def queue_marker(self) -> tuple[float, int]:
        return self._repo.marker()

    def expire_stale_commands(self, workstation_id: str) -> int:
        """Пометить сбойными команды, которые машина забрала и не подтвердила.

        Подтверждение может не прийти совсем: агента убили между исполнением и
        отчётом, или компьютер выключили той же командой. Вечное «на
        компьютере» в панели врёт хуже, чем признание через четверть часа.
        """
        workstation = self._repo.get(workstation_id)
        if not workstation:
            return 0
        commands = list(workstation.get("commands") or [])
        changed = 0
        for command in commands:
            if command.get("status") != "sent":
                continue
            if _is_fresh(command.get("created_at"), STALE_COMMAND_SECONDS):
                continue
            command["status"] = "failed"
            command["result"] = "компьютер не подтвердил выполнение"
            changed += 1
        if changed:
            self._repo.replace_commands(workstation_id, commands)
        return changed

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
