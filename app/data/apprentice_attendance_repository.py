"""Repository for manually-added apprentice attendance marks.

Turnstile registrations (Agbis DOC_REGISTR_EMPLOYEES) are the primary
source for "day of training" in the apprentice stipend report — see
masters_service.get_apprentice_stipends. This repository backs the
fallback for when that badge-in never happened (forgotten badge,
turnstile down, an off-site training day) but the admin still wants the
day counted: a manual mark, one row per (employee_id, date).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.settings import settings

DEFAULT_FILE = "apprentice_attendance_marks.json"


class ApprenticeAttendanceRepository:
    """Stores {employee_id, date, note, author, created_at} records, one per
    (employee_id, date) — adding again for the same day overwrites the note
    rather than duplicating the mark."""

    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file = Path(file_path or getattr(settings, "apprentice_attendance_file", DEFAULT_FILE))
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

    def _find(self, employee_id: str, day: str) -> dict[str, Any] | None:
        for rec in self._data:
            if rec.get("employee_id") == str(employee_id) and rec.get("date") == day:
                return rec
        return None

    def list_for_range(self, date_from: date, date_to: date) -> list[dict[str, Any]]:
        """All marks with date in [date_from, date_to] (inclusive), across
        every employee — merged into the stipend report per employee_id
        there."""
        df, dt = date_from.isoformat(), date_to.isoformat()
        return [rec for rec in self._data if df <= str(rec.get("date")) <= dt]

    def add_mark(self, employee_id: str, day: date, note: str = "", author: str = "") -> dict[str, Any]:
        day_iso = day.isoformat()
        rec = self._find(employee_id, day_iso)
        if rec:
            rec["note"] = note
            rec["author"] = author
            rec["updated_at"] = datetime.now().isoformat()
        else:
            rec = {
                "employee_id": str(employee_id),
                "date": day_iso,
                "note": note,
                "author": author,
                "created_at": datetime.now().isoformat(),
            }
            self._data.append(rec)
        self._save()
        return rec

    def remove_mark(self, employee_id: str, day: date) -> bool:
        rec = self._find(employee_id, day.isoformat())
        if rec:
            self._data.remove(rec)
            self._save()
            return True
        return False


_repo: ApprenticeAttendanceRepository | None = None


def get_apprentice_attendance_repository() -> ApprenticeAttendanceRepository:
    global _repo
    if _repo is None:
        _repo = ApprenticeAttendanceRepository()
    return _repo
