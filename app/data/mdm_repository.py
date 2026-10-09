"""Хранилище телефонов под MDM-управлением.

Файловое JSON-хранилище по образцу остальных репозиториев: перед каждой мутацией
перечитываем файл с диска, потому что процессов, пишущих в него, может быть
больше одного (bot-app и bot-main живут раздельно).

05.10.2026 реестр всех телефонов превратился в «[]». Список тогда жил в
self._data, общем для всех запросов процесса, а запросы телефонов идут
параллельно. Один поток прочитал файл в момент его перезаписи (запись была
«обрезать и писать»), получил ошибку разбора, которую _load молча превращал в
пустой список, и положил его в self._data — а соседний поток в это же время
сохранял self._data. Телефоны остались с токенами, которых сервер больше не
знал, и получают 401. Поэтому теперь:
- у каждой операции своя свежая копия списка, мутации — под замком;
- запись атомарная (временный файл + замена): читатель видит либо старое,
  либо новое содержимое, но не обрезанное;
- нечитаемый файл — ошибка, а не пустой реестр: один 500 лучше, чем
  перезаписать живые данные пустотой;
- перед каждой записью прежняя версия копируется в .bak.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional

from app.config import MDM_DEVICES_FILE

# Сколько последних команд храним в карточке устройства. История нужна, чтобы
# видеть, что телефон реально выполнил, но расти бесконечно ей незачем.
MAX_COMMAND_HISTORY = 50


class MdmRepository:
    _lock = threading.RLock()

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or MDM_DEVICES_FILE

    def _load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self._file):
            return []
        last_error: Optional[Exception] = None
        # os.replace на Windows может на миг держать файл — пара повторов.
        for _ in range(5):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, list):
                    raise ValueError("ожидался список устройств")
                return data
            except (OSError, ValueError) as exc:
                last_error = exc
                time.sleep(0.05)
        raise RuntimeError(f"Не удалось прочитать {self._file}: {last_error}")

    def _save(self, data: List[Dict[str, Any]]) -> None:
        directory = os.path.dirname(os.path.abspath(self._file))
        fd, tmp = tempfile.mkstemp(prefix=".mdm_devices.", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            if os.path.exists(self._file) and os.path.getsize(self._file) > 2:
                shutil.copyfile(self._file, self._file + ".bak")
            for attempt in range(10):
                try:
                    os.replace(tmp, self._file)
                    break
                except PermissionError:
                    if attempt == 9:
                        raise
                    time.sleep(0.05)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

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
        return sorted(self._load(), key=lambda d: str(d.get("last_seen_at") or ""), reverse=True)

    def get(self, device_id: str) -> Optional[Dict[str, Any]]:
        return next((d for d in self._load() if str(d.get("id")) == str(device_id)), None)

    def get_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        # secrets.compare_digest — токен приходит снаружи, сравнение по времени
        # не должно зависеть от того, сколько символов совпало.
        for device in self._load():
            stored = str(device.get("token") or "")
            if stored and secrets.compare_digest(stored, token):
                return device
        return None

    # --- запись ---------------------------------------------------------

    def upsert(self, device_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            data = self._load()
            for device in data:
                if str(device.get("id")) == str(device_id):
                    device.update(patch)
                    self._save(data)
                    return device
            device = {"id": device_id, **patch}
            data.append(device)
            self._save(data)
            return device

    def issue_token(self, device_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self.upsert(device_id, {"token": token})
        return token

    def delete(self, device_id: str) -> bool:
        with self._lock:
            data = self._load()
            kept = [d for d in data if str(d.get("id")) != str(device_id)]
            if len(kept) == len(data):
                return False
            self._save(kept)
            return True

    # --- команды --------------------------------------------------------

    def add_command(self, device_id: str, command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            data = self._load()
            for device in data:
                if str(device.get("id")) != str(device_id):
                    continue
                commands = list(device.get("commands") or [])
                commands.append(command)
                device["commands"] = commands[-MAX_COMMAND_HISTORY:]
                self._save(data)
                return command
            return None

    def take_pending(self, device_id: str) -> List[Dict[str, Any]]:
        """Отдаёт ожидающие команды и помечает их отправленными.

        Помечаем именно "sent", а не "done": подтверждение придёт отдельным
        ack-ом со следующего чек-ина, и до тех пор непонятно, выполнилась ли
        команда на телефоне вообще.
        """
        with self._lock:
            data = self._load()
            for device in data:
                if str(device.get("id")) != str(device_id):
                    continue
                pending = [c for c in (device.get("commands") or []) if c.get("status") == "pending"]
                for command in pending:
                    command["status"] = "sent"
                if pending:
                    self._save(data)
                return pending
            return []

    def cancel_command(self, device_id: str, command_id: str) -> bool:
        """Снять команду с очереди. Только ожидающую: отправленная уже на телефоне."""
        with self._lock:
            data = self._load()
            for device in data:
                if str(device.get("id")) != str(device_id):
                    continue
                for command in device.get("commands") or []:
                    if str(command.get("id")) != str(command_id):
                        continue
                    if command.get("status") != "pending":
                        return False
                    command["status"] = "canceled"
                    command["result"] = "отменено оператором"
                    self._save(data)
                    return True
            return False

    def ack_command(
        self, device_id: str, command_id: str, status: str, result: Optional[str], acked_at: str
    ) -> bool:
        with self._lock:
            data = self._load()
            for device in data:
                if str(device.get("id")) != str(device_id):
                    continue
                for command in device.get("commands") or []:
                    if str(command.get("id")) == str(command_id):
                        command["status"] = status
                        command["result"] = result
                        command["acked_at"] = acked_at
                        self._save(data)
                        return True
            return False


_repo: Optional[MdmRepository] = None


def get_mdm_repository() -> MdmRepository:
    global _repo
    if _repo is None:
        _repo = MdmRepository()
    return _repo
