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
# km_explicit holds a directly-known distance (e.g. GPS-track length for a beacon
# without an odometer); otherwise km is computed as odometer_end − odometer_start.
DEFAULTS = {"odometer_start": None, "odometer_end": None, "km_explicit": None,
            "source": "manual", "updated_at": None}


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
        km = entry.get("km_explicit")
        if km is None:
            s, e = entry.get("odometer_start"), entry.get("odometer_end")
            km = round(e - s, 1) if isinstance(s, (int, float)) and isinstance(e, (int, float)) and e >= s else None
        return {**entry, "km": km}

    def get(self, employee_code: str, period: str) -> dict[str, Any]:
        return self._with_km({**DEFAULTS, **self._data.get(self._key(employee_code, period), {})})

    def upsert(self, employee_code: str, period: str, **fields) -> dict[str, Any]:
        key = self._key(employee_code, period)
        cur = self._data.get(key, {})

        # Mileage physically cannot decrease. StarLine's /ways recompute is not
        # guaranteed monotonic while "today" is still in progress (its own
        # server-side filtering re-processes the still-forming daily track
        # between calls), so an auto-sync can legitimately return a smaller
        # number than a previous sync of the same period. A manual correction
        # (source="manual") is the one case that should always win outright —
        # anything else is floored at whatever is already on record.
        if fields.get("source") not in (None, "manual"):
            prev_km = self._with_km({**DEFAULTS, **cur}).get("km")
            if prev_km is not None:
                if fields.get("km_explicit") is not None and fields["km_explicit"] < prev_km:
                    fields = {**fields, "km_explicit": prev_km}
                new_end = fields.get("odometer_end")
                old_end = cur.get("odometer_end")
                if new_end is not None and old_end is not None and new_end < old_end:
                    fields = {**fields, "odometer_end": old_end}

        # explicit None is meaningful for these (clear the value)
        for k in ("odometer_start", "odometer_end", "km_explicit", "source"):
            if k in fields:
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
