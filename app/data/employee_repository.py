from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from datetime import date
from typing import List

from app.core.types import Employee, EmployeeStatus
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


class EmployeeRepository:
    """Repository for employees."""

    def __init__(self, storage: JsonStorage | None = None) -> None:
        self._storage = storage or JsonStorage(DATA_FILE)
        self._data: dict[str, dict] = self._storage.load() or {}

    def _save(self) -> None:
        self._storage.save(self._data)

    @staticmethod
    def _parse_date(value) -> date | None:
        if not value:
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except Exception:
            return None

    def list_employees(self) -> List[Employee]:
        employees: List[Employee] = []
        for uid, data in self._data.items():
            if not isinstance(data, dict):
                continue
            record = {
                "id": str(uid),
                "name": data.get("name", ""),
                "full_name": data.get("full_name", ""),
                "phone": data.get("phone", ""),
                "card_number": data.get("card_number", ""),
                "bank": data.get("bank", ""),
                "birthdate": self._parse_date(data.get("birthdate")),
                "note": data.get("note", ""),
                "photo_url": data.get("photo_url", ""),
                "status": EmployeeStatus(data.get("status", "active")),
            }
            employees.append(Employee(**record))
        return employees

    def add_employee(self, employee: Employee) -> None:
        data = _serialize(employee)
        data.pop("id", None)
        self._data[employee.id] = data
        self._save()

    def update_employee(self, employee: Employee) -> None:
        if employee.id in self._data:
            data = _serialize(employee)
            data.pop("id", None)
            self._data[employee.id].update(data)
            self._save()

    def delete_employee_by_id(self, employee_id: str) -> None:
        if employee_id in self._data:
            self._data.pop(employee_id)
            self._save()

    def save_employees(self, employees: List[Employee]) -> None:
        self._data = {e.id: _serialize(e) | {"id": e.id} for e in employees}
        for v in self._data.values():
            v.pop("id", None)
        self._save()
