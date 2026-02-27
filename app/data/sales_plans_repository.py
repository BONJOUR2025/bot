"""Repository for employee sales plans (per-month or global)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.data.json_storage import JsonStorage
from app.settings import settings


@dataclass
class SalesPlan:
    """Sales plan for an employee, optionally tied to a specific month."""
    employee_code: str
    employee_name: str
    month_key: str | None = None   # e.g. "ЯНВАРЬ_2025"; None = global fallback
    repair_plan: float = 0.0
    cosmetics_plan: float = 0.0
    shoes_plan: float = 0.0
    ignore_kpi: bool = False
    force_max: list = field(default_factory=list)
    force_min: list = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "employee_code": self.employee_code,
            "employee_name": self.employee_name,
            "month_key": self.month_key,
            "repair_plan": self.repair_plan,
            "cosmetics_plan": self.cosmetics_plan,
            "shoes_plan": self.shoes_plan,
            "ignore_kpi": self.ignore_kpi,
            "force_max": self.force_max,
            "force_min": self.force_min,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SalesPlan:
        return cls(
            employee_code=str(data.get("employee_code", "")),
            employee_name=str(data.get("employee_name", "")),
            month_key=data.get("month_key") or None,
            repair_plan=float(data.get("repair_plan", 0)),
            cosmetics_plan=float(data.get("cosmetics_plan", 0)),
            shoes_plan=float(data.get("shoes_plan", 0)),
            ignore_kpi=bool(data.get("ignore_kpi", False)),
            force_max=list(data.get("force_max") or []),
            force_min=list(data.get("force_min") or []),
        )


def _plan_key(month_key: str | None, employee_code: str) -> str:
    if month_key:
        return f"{month_key}|{employee_code}"
    return employee_code


class SalesPlansRepository:
    """Plans can be global (month_key=None) or month-specific (month_key="ЯНВАРЬ_2025").
    Month-specific plans override global ones when calculating payroll for that month.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.storage = JsonStorage(path or settings.sales_plans_file)
        self._plans: dict[str, SalesPlan] = {}
        self._load()

    def _load(self) -> None:
        data = self.storage.load()
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("employee_code"):
                    plan = SalesPlan.from_dict(item)
                    key = _plan_key(plan.month_key, plan.employee_code)
                    self._plans[key] = plan

    def _save(self) -> None:
        data = [plan.to_dict() for plan in self._plans.values()]
        self.storage.save(data)

    def list_plans(self, month_key: str | None = None) -> list[SalesPlan]:
        if month_key is None:
            return list(self._plans.values())
        return [p for p in self._plans.values() if p.month_key == month_key]

    def get_plan(self, employee_code: str, month_key: str | None = None) -> SalesPlan | None:
        if month_key:
            specific = self._plans.get(_plan_key(month_key, employee_code))
            if specific:
                return specific
        return self._plans.get(employee_code)  # global fallback

    def set_plan(
        self,
        employee_code: str,
        employee_name: str,
        month_key: str | None = None,
        repair_plan: float | None = None,
        cosmetics_plan: float | None = None,
        shoes_plan: float | None = None,
        ignore_kpi: bool | None = None,
        force_max: list | None = None,
        force_min: list | None = None,
    ) -> SalesPlan:
        key = _plan_key(month_key, employee_code)
        existing = self._plans.get(key)
        if existing:
            if repair_plan is not None:
                existing.repair_plan = repair_plan
            if cosmetics_plan is not None:
                existing.cosmetics_plan = cosmetics_plan
            if shoes_plan is not None:
                existing.shoes_plan = shoes_plan
            if ignore_kpi is not None:
                existing.ignore_kpi = ignore_kpi
            if force_max is not None:
                existing.force_max = force_max
            if force_min is not None:
                existing.force_min = force_min
            existing.employee_name = employee_name
            plan = existing
        else:
            plan = SalesPlan(
                employee_code=employee_code,
                employee_name=employee_name,
                month_key=month_key,
                repair_plan=repair_plan or 0.0,
                cosmetics_plan=cosmetics_plan or 0.0,
                shoes_plan=shoes_plan or 0.0,
                ignore_kpi=ignore_kpi or False,
                force_max=force_max or [],
                force_min=force_min or [],
            )
            self._plans[key] = plan

        self._save()
        return plan

    def delete_plan(self, employee_code: str, month_key: str | None = None) -> bool:
        key = _plan_key(month_key, employee_code)
        if key in self._plans:
            del self._plans[key]
            self._save()
            return True
        return False

    def get_plans_map(self, month_key: str | None = None) -> dict[str, SalesPlan]:
        """Returns dict keyed by employee_code.
        Month-specific plans override global ones.
        """
        result: dict[str, SalesPlan] = {}
        for plan in self._plans.values():
            if plan.month_key is None:
                result[plan.employee_code] = plan
        if month_key:
            for plan in self._plans.values():
                if plan.month_key == month_key:
                    result[plan.employee_code] = plan
        return result


_repository: SalesPlansRepository | None = None


def get_sales_plans_repository() -> SalesPlansRepository:
    global _repository
    if _repository is None:
        _repository = SalesPlansRepository()
    return _repository
