"""Per-manager monthly plan (оклад, KPI, план выручки, плановые конверсии).

Edited on the «Планы продаж» page, consumed by the manager salary page.
Keyed by (employee_code, period) where period is "YYYY-MM".
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.settings import settings

DEFAULT_FILE = "manager_plans.json"

DEFAULTS = {
    "oklad": 0,
    "kpi_max": 0,
    "revenue_plan": 0,
    "repair_plan_conv": 0.50,
    "sew_plan_conv": 0.25,
}


class ManagerPlanRepository:
    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file = Path(file_path or getattr(settings, "manager_plans_file", DEFAULT_FILE))
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
        stored = self._data.get(self._key(employee_code, period), {})
        return {**DEFAULTS, **stored}

    def list(self, period: str) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        suffix = f"__{period}"
        for key, val in self._data.items():
            if key.endswith(suffix):
                code = key[: -len(suffix)]
                out[code] = {**DEFAULTS, **val}
        return out

    def upsert(self, employee_code: str, period: str, **fields) -> dict[str, Any]:
        key = self._key(employee_code, period)
        cur = self._data.get(key, {})
        for k in DEFAULTS:
            if k in fields and fields[k] is not None:
                cur[k] = fields[k]
        self._data[key] = cur
        self._save()
        return {**DEFAULTS, **cur}


_repo: ManagerPlanRepository | None = None


def get_manager_plan_repository() -> ManagerPlanRepository:
    global _repo
    if _repo is None:
        _repo = ManagerPlanRepository()
    return _repo
