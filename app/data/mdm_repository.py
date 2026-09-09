"""Хранилище телефонов под MDM-управлением.

Файловое JSON-хранилище по образцу остальных репозиториев: перед каждой мутацией
перечитываем файл с диска, потому что процессов, пишущих в него, может быть
больше одного (bot-app и bot-main живут раздельно).
"""

from __future__ import annotations

import json
import os
import secrets
from typing import Any, Dict, List, Optional

from app.config import MDM_DEVICES_FILE

# Сколько последних команд храним в карточке устройства. История нужна, чтобы
# видеть, что телефон реально выполнил, но расти бесконечно ей незачем.
MAX_COMMAND_HISTORY = 50


class MdmRepository:
    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or MDM_DEVICES_FILE
        self._data: List[Dict[str, Any]] = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self._file):
            return []
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self) -> None:
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    # --- чтение ---------------------------------------------------------

    def marker(self) -> tuple[float, int]:
        """Дешёвый признак «файл менялся»: время правки и размер.

        Нужен длинному опросу: он ждёт команду в цикле и не может перечитывать
        весь JSON по нескольку раз в секунду на каждый висящий телефон. Команду
        мог положить и другой процесс (bot-main исполняет расписания), поэтому
        признак берётся с диска, а не из памяти. Размер идёт рядом со временем
        на случай двух правок внутри одного тика файловой системы.
        """
        try:
            stat = os.stat(self._file)
            return (stat.st_mtime, stat.st_size)
        except OSError:
            return (0.0, 0)

    def list(self) -> List[Dict[str, Any]]:
        self._data = self._load()
        return sorted(self._data, key=lambda d: str(d.get("last_seen_at") or ""), reverse=True)

    def get(self, device_id: str) -> Optional[Dict[str, Any]]:
        self._data = self._load()
        return next((d for d in self._data if str(d.get("id")) == str(device_id)), None)

    def get_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        self._data = self._load()
        # secrets.compare_digest — токен приходит снаружи, сравнение по времени
        # не должно зависеть от того, сколько символов совпало.
        for device in self._data:
            stored = str(device.get("token") or "")
            if stored and secrets.compare_digest(stored, token):
                return device
        return None

    # --- запись ---------------------------------------------------------

    def upsert(self, device_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        self._data = self._load()
        for device in self._data:
            if str(device.get("id")) == str(device_id):
                device.update(patch)
                self._save()
                return device
        device = {"id": device_id, **patch}
        self._data.append(device)
        self._save()
        return device

    def issue_token(self, device_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self.upsert(device_id, {"token": token})
        return token

    def delete(self, device_id: str) -> bool:
        self._data = self._load()
        before = len(self._data)
        self._data = [d for d in self._data if str(d.get("id")) != str(device_id)]
        if len(self._data) == before:
            return False
        self._save()
        return True

    # --- команды --------------------------------------------------------

    def add_command(self, device_id: str, command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        self._data = self._load()
        for device in self._data:
            if str(device.get("id")) != str(device_id):
                continue
            commands = list(device.get("commands") or [])
            commands.append(command)
            device["commands"] = commands[-MAX_COMMAND_HISTORY:]
            self._save()
            return command
        return None

    def take_pending(self, device_id: str) -> List[Dict[str, Any]]:
        """Отдаёт ожидающие команды и помечает их отправленными.

        Помечаем именно "sent", а не "done": подтверждение придёт отдельным
        ack-ом со следующего чек-ина, и до тех пор непонятно, выполнилась ли
        команда на телефоне вообще.
        """
        self._data = self._load()
        for device in self._data:
            if str(device.get("id")) != str(device_id):
                continue
            pending = [c for c in (device.get("commands") or []) if c.get("status") == "pending"]
            for command in pending:
                command["status"] = "sent"
            if pending:
                self._save()
            return pending
        return []

    def ack_command(
        self, device_id: str, command_id: str, status: str, result: Optional[str], acked_at: str
    ) -> bool:
        self._data = self._load()
        for device in self._data:
            if str(device.get("id")) != str(device_id):
                continue
            for command in device.get("commands") or []:
                if str(command.get("id")) == str(command_id):
                    command["status"] = status
                    command["result"] = result
                    command["acked_at"] = acked_at
                    self._save()
                    return True
        return False


_repo: Optional[MdmRepository] = None


def get_mdm_repository() -> MdmRepository:
    global _repo
    if _repo is None:
        _repo = MdmRepository()
    return _repo
