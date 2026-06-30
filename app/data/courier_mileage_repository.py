"""Per-courier monthly car mileage (пробег авто).

Keyed by (employee_code, period). Stores the odometer at the start and end of the
period; пробег = end − start. ``end`` can be filled from StarLine (sync) or by
hand; ``source`` records where the current value came from.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.settings import settings

DEFAULT_FILE = "courier_mileage.json"
DEFAULTS = {"odometer_start": None, "odometer_end": None, "source": "manual", "updated_at": None}


class CourierMileageRepository:
    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file = Path(file_path or getattr(settings, "courier_mileage_file", DEFAULT_FILE))
        self._data: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self._file.exists():
            return {}
        try:
            with open(self._file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self) -> None:
        try:
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @staticmethod
    def _key(employee_code: str, period: str) -> str:
        return f"{employee_code}__{period}"

    @staticmethod
    def _with_km(entry: dict[str, Any]) -> dict[str, Any]:
        s, e = entry.get("odometer_start"), entry.get("odometer_end")
        km = round(e - s, 1) if isinstance(s, (int, float)) and isinstance(e, (int, float)) and e >= s else None
        return {**entry, "km": km}

    def get(self, employee_code: str, period: str) -> dict[str, Any]:
        return self._with_km({**DEFAULTS, **self._data.get(self._key(employee_code, period), {})})

    def upsert(self, employee_code: str, period: str, **fields) -> dict[str, Any]:
        key = self._key(employee_code, period)
        cur = self._data.get(key, {})
        for k in ("odometer_start", "odometer_end", "source"):
            if k in fields and fields[k] is not None:
                cur[k] = fields[k]
        cur["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._data[key] = cur
        self._save()
        return self.get(employee_code, period)


_repo: CourierMileageRepository | None = None


def get_courier_mileage_repository() -> CourierMileageRepository:
    global _repo
    if _repo is None:
        _repo = CourierMileageRepository()
    return _repo
