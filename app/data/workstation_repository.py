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
