from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from datetime import date, datetime
from typing import List

from app.core.types import Employee, EmployeeStatus
from app.utils.config import DATA_FILE
from app.utils.logger import log
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
        log(f"📂 Loading employees from {self._storage.path}")
        self._data: dict[str, dict] = self._storage.load() or {}
        log(f"✅ Loaded employees: {len(self._data)}")
        if not self._data:
            log("⚠️ EmployeeRepository loaded no employees")

    def _save(self) -> None:
        self._storage.save(self._data)

    def _create_employee(self, uid: str, data: dict) -> Employee:
        record = {
            "id": str(uid),
            "name": data.get("name", ""),
            "full_name": data.get("full_name", ""),
            "phone": data.get("phone", ""),
            "position": data.get("position", ""),
            "is_admin": data.get("is_admin", False),
            "card_number": data.get("card_number", ""),
            "bank": data.get("bank", ""),
            "work_place": data.get("work_place", ""),
            "clothing_size": data.get("clothing_size", ""),
            "birthdate": self._parse_date(data.get("birthdate")),
            "note": data.get("note", ""),
            "photo_url": data.get("photo_url", ""),
            "status": EmployeeStatus(data.get("status", "active")),
            "created_at": self._parse_datetime(data.get("created_at"))
            or datetime.utcnow(),
            "tags": data.get("tags", []),
            "payout_chat_key": data.get("payout_chat_key"),
        }
        return Employee(**record)

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

    @staticmethod
    def _parse_datetime(value) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except Exception:
            return None

    def list_employees(self, **filters) -> List[Employee]:
        """Return employees optionally filtered by provided criteria."""
        employees: List[Employee] = []
        for uid, data in self._data.items():
            if not isinstance(data, dict):
                continue
            emp = self._create_employee(uid, data)
            if filters:
                status = filters.get("status")
                if status and emp.status.value not in (status if isinstance(status, list) else [status]):
                    continue
                position = filters.get("position")
                if position and emp.position not in (position if isinstance(position, list) else [position]):
                    continue
                birthday_today = filters.get("birthday_today")
                if birthday_today:
                    if not emp.birthdate or emp.birthdate.timetuple()[1:3] != datetime.utcnow().date().timetuple()[1:3]:
                        continue
                tags = filters.get("tags")
                if tags:
                    if not set(tags).intersection(set(emp.tags)):
                        continue
            employees.append(emp)
        return employees

    def get_employee(self, employee_id: str) -> Employee | None:
        data = self._data.get(str(employee_id))
        if not isinstance(data, dict):
            return None
        try:
            return self._create_employee(str(employee_id), data)
        except Exception as exc:
            log(f"⚠️ Failed to parse employee {employee_id}: {exc}")
            return None

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
