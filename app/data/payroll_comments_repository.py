"""Repository for payroll comments — per employee per month notes by admin."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.settings import settings

DEFAULT_FILE = "payroll_comments.json"


class PayrollCommentsRepository:
    """Stores {month_key, employee_code, comment, updated_at} records."""

    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file = Path(file_path or getattr(settings, "payroll_comments_file", DEFAULT_FILE))
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

    def get_comments_map(self, month_key: str) -> dict[str, str]:
        """Return {employee_code: comment} for a given month."""
        return {
            rec["employee_code"]: rec.get("comment", "")
            for rec in self._data
            if rec.get("month_key") == month_key and rec.get("comment")
        }

    def set_comment(self, month_key: str, employee_code: str, comment: str) -> dict[str, Any]:
        rec = self._find(month_key, employee_code)
        if rec:
            rec["comment"] = comment
            rec["updated_at"] = datetime.now().isoformat()
        else:
            rec = {
                "month_key": month_key,
                "employee_code": employee_code,
                "comment": comment,
                "updated_at": datetime.now().isoformat(),
            }
            self._data.append(rec)
        self._save()
        return rec

    def delete_comment(self, month_key: str, employee_code: str) -> bool:
        rec = self._find(month_key, employee_code)
        if rec:
            self._data.remove(rec)
            self._save()
            return True
        return False


_repo: PayrollCommentsRepository | None = None


def get_payroll_comments_repository() -> PayrollCommentsRepository:
    global _repo
    if _repo is None:
        _repo = PayrollCommentsRepository()
    return _repo
