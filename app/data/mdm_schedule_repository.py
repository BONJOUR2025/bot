"""Хранилище расписаний команд MDM.

Расписание — «делать команду X каждый день в HH:MM для таких-то телефонов».
Файловое JSON-хранилище по образцу остальных: перечитываем перед мутацией,
потому что процессов может быть больше одного (bot-main владеет задачей-таймером,
bot-app правит расписания из панели).
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Optional

from app.config import MDM_SCHEDULES_FILE


class MdmScheduleRepository:
    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or MDM_SCHEDULES_FILE

    def _load(self) -> list[dict[str, Any]]:
        if not os.path.exists(self._file):
            return []
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, data: list[dict[str, Any]]) -> None:
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def list(self) -> list[dict[str, Any]]:
        return self._load()

    def add(self, schedule: dict[str, Any]) -> dict[str, Any]:
        data = self._load()
        schedule["id"] = uuid.uuid4().hex
        data.append(schedule)
        self._save(data)
        return schedule

    def delete(self, schedule_id: str) -> bool:
        data = self._load()
        remaining = [s for s in data if str(s.get("id")) != str(schedule_id)]
        if len(remaining) == len(data):
            return False
        self._save(remaining)
        return True

    def mark_run(self, schedule_id: str, run_date: str) -> None:
        data = self._load()
        for s in data:
            if str(s.get("id")) == str(schedule_id):
                s["last_run_date"] = run_date
                break
        self._save(data)


_repo: Optional[MdmScheduleRepository] = None


def get_mdm_schedule_repository() -> MdmScheduleRepository:
    global _repo
    if _repo is None:
        _repo = MdmScheduleRepository()
    return _repo
