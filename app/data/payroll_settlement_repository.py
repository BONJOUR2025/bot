"""Repository for payroll settlements — tracks final salary payment per employee per month."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from app.settings import settings

DEFAULT_FILE = "payroll_settlements.json"


class PayrollSettlementRepository:
    """Stores {month_key, employee_code, paid, paid_at} records."""

    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file = Path(file_path or getattr(settings, "payroll_settlements_file", DEFAULT_FILE))
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

    def _find(self, month_key: str, employee_code: str) -> dict[str, Any] | None:
        for rec in self._data:
            if rec.get("month_key") == month_key and rec.get("employee_code") == employee_code:
                return rec
        return None

    def get_settlements_map(self, month_key: str) -> dict[str, bool]:
        """Return {employee_code: paid} for a given month."""
        self._data = self._load()  # always fresh from disk (two-process setup)
        return {
            rec["employee_code"]: bool(rec.get("paid", False))
            for rec in self._data
            if rec.get("month_key") == month_key
        }

    def set_settlement(self, month_key: str, employee_code: str, paid: bool) -> dict[str, Any]:
        self._data = self._load()  # sync with disk before mutating
        rec = self._find(month_key, employee_code)
        if rec:
            rec["paid"] = paid
            rec["paid_at"] = datetime.now().isoformat() if paid else None
        else:
            rec = {
                "month_key": month_key,
                "employee_code": employee_code,
                "paid": paid,
                "paid_at": datetime.now().isoformat() if paid else None,
            }
            self._data.append(rec)
        self._save()
        return rec


_repo: PayrollSettlementRepository | None = None


def get_payroll_settlement_repository() -> PayrollSettlementRepository:
    global _repo
    if _repo is None:
        _repo = PayrollSettlementRepository()
    return _repo
