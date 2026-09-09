"""Хранилище салонных компьютеров. JSON-файл, как у остальных репозиториев.

Перечитываем перед каждой мутацией: писать может и bot-app (отчёты агентов),
и bot-main (сторож гасит признак тревоги), а это разные процессы.
"""

from __future__ import annotations

import json
import os
import secrets
from typing import Any, Dict, List, Optional

from app.config import WORKSTATIONS_FILE

# Сколько последних команд держим в карточке. История нужна, чтобы видеть,
# что машина реально выполнила, но расти бесконечно ей незачем.
MAX_COMMAND_HISTORY = 50


class WorkstationRepository:
    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or WORKSTATIONS_FILE

    def _load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self._file):
            return []
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, data: List[Dict[str, Any]]) -> None:
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def list(self) -> List[Dict[str, Any]]:
        return sorted(self._load(), key=lambda w: str(w.get("last_seen_at") or ""), reverse=True)

    def get(self, workstation_id: str) -> Optional[Dict[str, Any]]:
        return next((w for w in self._load() if str(w.get("id")) == str(workstation_id)), None)

    def get_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        for w in self._load():
            stored = str(w.get("token") or "")
            # compare_digest — токен приходит снаружи, сравнение по времени
            # не должно подсказывать, сколько символов совпало.
            if stored and secrets.compare_digest(stored, token):
                return w
        return None

    def upsert(self, workstation_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        data = self._load()
        for w in data:
            if str(w.get("id")) == str(workstation_id):
                w.update(patch)
                self._save(data)
                return w
        created = {"id": str(workstation_id), **patch}
        data.append(created)
        self._save(data)
        return created

    # --- очередь команд --------------------------------------------------
    # Форма повторяет очередь MDM телефонов сознательно: там она выстрадана
    # (подтверждения приходят отдельно, зависшие подметаются, отменить можно
    # только неотправленное). Повторяем форму, а не переиспользуем код, чтобы
    # правки для ПК не задевали работающий парк телефонов.

    def marker(self) -> tuple[float, int]:
        """Дешёвый признак «файл менялся» для длинного опроса: время и размер.

        Команду мог положить и другой процесс, поэтому признак берём с диска.
        Размер рядом со временем — на случай двух правок внутри одного тика
        файловой системы.
        """
        try:
            stat = os.stat(self._file)
            return (stat.st_mtime, stat.st_size)
        except OSError:
            return (0.0, 0)

    def add_command(self, workstation_id: str, command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        data = self._load()
        for w in data:
            if str(w.get("id")) != str(workstation_id):
                continue
            commands = list(w.get("commands") or [])
            commands.append(command)
            w["commands"] = commands[-MAX_COMMAND_HISTORY:]
            self._save(data)
            return command
        return None

    def take_pending(self, workstation_id: str) -> List[Dict[str, Any]]:
        """Отдаёт ожидающие команды и помечает отправленными.

        Именно "sent", а не "done": подтверждение придёт отдельно, и до тех пор
        неизвестно, выполнилась ли команда на машине вообще.
        """
        data = self._load()
        for w in data:
            if str(w.get("id")) != str(workstation_id):
                continue
            pending = [c for c in (w.get("commands") or []) if c.get("status") == "pending"]
            for command in pending:
                command["status"] = "sent"
            if pending:
                self._save(data)
            return pending
        return []

    def ack_command(self, workstation_id: str, command_id: str, status: str,
                    result: Optional[str], acked_at: str) -> bool:
        data = self._load()
        for w in data:
            if str(w.get("id")) != str(workstation_id):
                continue
            for command in w.get("commands") or []:
                if str(command.get("id")) == str(command_id):
                    command["status"] = status
                    command["result"] = result
                    command["acked_at"] = acked_at
                    self._save(data)
                    return True
        return False

    def cancel_command(self, workstation_id: str, command_id: str) -> bool:
        """Снять команду с очереди. Только ожидающую: отправленная уже на машине."""
        data = self._load()
        for w in data:
            if str(w.get("id")) != str(workstation_id):
                continue
            for command in w.get("commands") or []:
                if str(command.get("id")) != str(command_id):
                    continue
                if command.get("status") != "pending":
                    return False
                command["status"] = "canceled"
                command["result"] = "отменено оператором"
                self._save(data)
                return True
        return False

    def replace_commands(self, workstation_id: str, commands: List[Dict[str, Any]]) -> None:
        data = self._load()
        for w in data:
            if str(w.get("id")) == str(workstation_id):
                w["commands"] = commands
                self._save(data)
                return

    def delete(self, workstation_id: str) -> bool:
        data = self._load()
        remaining = [w for w in data if str(w.get("id")) != str(workstation_id)]
        if len(remaining) == len(data):
            return False
        self._save(remaining)
        return True


_repo: Optional[WorkstationRepository] = None


def get_workstation_repository() -> WorkstationRepository:
    global _repo
    if _repo is None:
        _repo = WorkstationRepository()
    return _repo
