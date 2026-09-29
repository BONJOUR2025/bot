"""Деление одной услуги между несколькими мастерами.

В Агбисе у услуги один выход — и вся зарплата по ней уходит тому, кто его
отсканировал. Когда пару делали двое (один снял подошву, другой приклеил),
старший мастер делит услугу здесь: мастера и их доли. Сам Агбис не трогаем —
деление накладывается при чтении отчёта (service_split_service), поэтому
видно сразу и снимается одним удалением.

JSON-файл, как у остальных наших репозиториев; перечитываем перед записью.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import SERVICE_SPLITS_FILE


def _load(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(path: str, data: dict[str, Any]) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


class ServiceSplitRepository:
    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or SERVICE_SPLITS_FILE

    def all(self) -> dict[int, dict[str, Any]]:
        out = {}
        for key, rec in _load(self._file).items():
            try:
                out[int(key)] = rec
            except ValueError:
                continue
        return out

    def get(self, service_id: int) -> Optional[dict[str, Any]]:
        return _load(self._file).get(str(int(service_id)))

    def set(self, service_id: int, parts: list[dict[str, Any]], *, by: str,
            doc_num: str = "", service_name: str = "") -> dict[str, Any]:
        data = _load(self._file)
        rec = {"parts": parts, "by": by, "at": datetime.now(timezone.utc).isoformat(),
               "doc_num": doc_num, "service_name": service_name}
        data[str(int(service_id))] = rec
        _save(self._file, data)
        return rec

    def delete(self, service_id: int) -> bool:
        data = _load(self._file)
        if data.pop(str(int(service_id)), None) is None:
            return False
        _save(self._file, data)
        return True
