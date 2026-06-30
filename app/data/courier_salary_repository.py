"""Repository for courier salary accruals (начисления), mirroring the manager one.

Stores each accrual with its breakdown and a link to the created payout, so the
courier page can show history and the numbers stay auditable.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.settings import settings

DEFAULT_FILE = "courier_salary_accruals.json"
MAX_ENTRIES = 5000


class CourierSalaryRepository:
    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file = Path(file_path or getattr(settings, "courier_salary_file", DEFAULT_FILE))
        self._data: list[dict[str, Any]] = self._load()

    def _load(self) -> list[dict[str, Any]]:
        if not self._file.exists():
            return []
        try:
            with open(self._file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self) -> None:
        try:
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add(self, entry: dict[str, Any]) -> dict[str, Any]:
        entry = dict(entry)
        entry["id"] = (max((e.get("id", 0) for e in self._data), default=0) + 1)
        entry.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
        self._data.append(entry)
        if len(self._data) > MAX_ENTRIES:
            self._data = self._data[-MAX_ENTRIES:]
        self._save()
        return entry

    def get(self, accrual_id: int) -> dict[str, Any] | None:
        return next((e for e in self._data if e.get("id") == accrual_id), None)

    def set_fields(self, accrual_id: int, **fields: Any) -> dict[str, Any] | None:
        for e in self._data:
            if e.get("id") == accrual_id:
                e.update(fields)
                self._save()
                return e
        return None

    def list(self, *, employee_code: str | None = None, period: str | None = None,
             limit: int = 200) -> list[dict[str, Any]]:
        rows = self._data
        if employee_code:
            rows = [e for e in rows if str(e.get("employee_code")) == str(employee_code)]
        if period:
            rows = [e for e in rows if e.get("period") == period]
        return list(reversed(rows))[:limit]

    def delete(self, accrual_id: int) -> bool:
        before = len(self._data)
        self._data = [e for e in self._data if e.get("id") != accrual_id]
        if len(self._data) != before:
            self._save()
            return True
        return False


_repo: CourierSalaryRepository | None = None


def get_courier_salary_repository() -> CourierSalaryRepository:
    global _repo
    if _repo is None:
        _repo = CourierSalaryRepository()
    return _repo
