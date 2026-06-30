"""Per-courier monthly plan: оклад (fixed salary) and the StarLine device id.

Keyed by (employee_code, period), period = "YYYY-MM". Mirrors the manager plan
repository, but the courier is on a fixed oklad (no KPI).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.settings import settings

DEFAULT_FILE = "courier_plans.json"
DEFAULTS = {"oklad": 0, "starline_device_id": ""}


class CourierPlanRepository:
    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file = Path(file_path or getattr(settings, "courier_plans_file", DEFAULT_FILE))
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

    def get(self, employee_code: str, period: str) -> dict[str, Any]:
        return {**DEFAULTS, **self._data.get(self._key(employee_code, period), {})}

    def list(self, period: str) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        suffix = f"__{period}"
        for key, val in self._data.items():
            if key.endswith(suffix):
                out[key[: -len(suffix)]] = {**DEFAULTS, **val}
        return out

    def all_device_ids(self) -> list[str]:
        """Distinct StarLine device ids across all plans (for the background poller)."""
        out = set()
        for v in self._data.values():
            d = v.get("starline_device_id")
            if d:
                out.add(str(d))
        return sorted(out)

    def upsert(self, employee_code: str, period: str, **fields) -> dict[str, Any]:
        key = self._key(employee_code, period)
        cur = self._data.get(key, {})
        for k in DEFAULTS:
            if k in fields and fields[k] is not None:
                cur[k] = fields[k]
        self._data[key] = cur
        self._save()
        return {**DEFAULTS, **cur}


_repo: CourierPlanRepository | None = None


def get_courier_plan_repository() -> CourierPlanRepository:
    global _repo
    if _repo is None:
        _repo = CourierPlanRepository()
    return _repo
