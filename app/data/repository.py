from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import List

from app.core.types import Employee
from app.utils.config import DATA_FILE
from .json_storage import JsonStorage


def _serialize(obj):
    if is_dataclass(obj):
        return {k: _serialize(v) for k, v in asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


class Repository:
    """Repository for employees."""

    def __init__(self, storage: JsonStorage | None = None) -> None:
        self._storage = storage or JsonStorage(DATA_FILE)
        self._data = self._storage.load() or {"employees": []}

    def _save(self) -> None:
        self._storage.save(self._data)

    def list_employees(self) -> List[Employee]:
        return [Employee(**e) for e in self._data.get("employees", [])]

    def save_employees(self, employees: List[Employee]) -> None:
        self._data["employees"] = [_serialize(e) for e in employees]
        self._save()
