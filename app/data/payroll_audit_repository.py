"""Repository for payroll audit log — tracks manual changes made by admins."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.settings import settings

DEFAULT_FILE = "payroll_audit.json"


class PayrollAuditRepository:
    """Stores audit log entries for manual payroll changes."""

    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file = Path(file_path or getattr(settings, "payroll_audit_file", DEFAULT_FILE))
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
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def add_entry(
        self,
        *,
        actor: str,
        action: str,
        employee_code: str,
        employee_name: str,
        month_key: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "id": len(self._data) + 1,
            "timestamp": datetime.now().isoformat(),
            "actor": actor,
            "action": action,
            "employee_code": employee_code,
            "employee_name": employee_name,
            "month_key": month_key,
            "details": details or {},
        }
        self._data.append(entry)
        self._save()
        return entry

    def get_entries(
        self,
        month_key: str | None = None,
        employee_code: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        result = self._data
        if month_key:
            result = [e for e in result if e.get("month_key") == month_key]
        if employee_code:
            result = [e for e in result if e.get("employee_code") == employee_code]
        # Return most recent first
        return list(reversed(result))[:limit]


_repo: PayrollAuditRepository | None = None


def get_payroll_audit_repository() -> PayrollAuditRepository:
    global _repo
    if _repo is None:
        _repo = PayrollAuditRepository()
    return _repo
