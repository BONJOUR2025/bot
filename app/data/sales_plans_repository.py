"""Repository for employee sales plans."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.data.json_storage import JsonStorage
from app.settings import settings


@dataclass
class SalesPlan:
    """Sales plan for an employee."""
    employee_code: str  # 4-digit code from employee name
    employee_name: str  # Full name for display
    repair_plan: float = 0.0  # Repair/dry cleaning sales plan
    cosmetics_plan: float = 0.0  # Cosmetics sales plan
    shoes_plan: float = 0.0  # Shoes sales plan

    def to_dict(self) -> dict[str, Any]:
        return {
            "employee_code": self.employee_code,
            "employee_name": self.employee_name,
            "repair_plan": self.repair_plan,
            "cosmetics_plan": self.cosmetics_plan,
            "shoes_plan": self.shoes_plan,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SalesPlan:
        return cls(
            employee_code=str(data.get("employee_code", "")),
            employee_name=str(data.get("employee_name", "")),
            repair_plan=float(data.get("repair_plan", 0)),
            cosmetics_plan=float(data.get("cosmetics_plan", 0)),
            shoes_plan=float(data.get("shoes_plan", 0)),
        )


class SalesPlansRepository:
    """Repository for managing employee sales plans."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.storage = JsonStorage(path or settings.sales_plans_file)
        self._plans: dict[str, SalesPlan] = {}
        self._load()

    def _load(self) -> None:
        """Load plans from storage."""
        data = self.storage.load()
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("employee_code"):
                    plan = SalesPlan.from_dict(item)
                    self._plans[plan.employee_code] = plan

    def _save(self) -> None:
        """Save plans to storage."""
        data = [plan.to_dict() for plan in self._plans.values()]
        self.storage.save(data)

    def list_plans(self) -> list[SalesPlan]:
        """List all sales plans."""
        return list(self._plans.values())

    def get_plan(self, employee_code: str) -> SalesPlan | None:
        """Get sales plan for an employee by code."""
        return self._plans.get(employee_code)

    def set_plan(
        self,
        employee_code: str,
        employee_name: str,
        repair_plan: float | None = None,
        cosmetics_plan: float | None = None,
        shoes_plan: float | None = None,
    ) -> SalesPlan:
        """Create or update a sales plan."""
        existing = self._plans.get(employee_code)
        if existing:
            if repair_plan is not None:
                existing.repair_plan = repair_plan
            if cosmetics_plan is not None:
                existing.cosmetics_plan = cosmetics_plan
            if shoes_plan is not None:
                existing.shoes_plan = shoes_plan
            existing.employee_name = employee_name
            plan = existing
        else:
            plan = SalesPlan(
                employee_code=employee_code,
                employee_name=employee_name,
                repair_plan=repair_plan or 0.0,
                cosmetics_plan=cosmetics_plan or 0.0,
                shoes_plan=shoes_plan or 0.0,
            )
            self._plans[employee_code] = plan

        self._save()
        return plan

    def delete_plan(self, employee_code: str) -> bool:
        """Delete a sales plan."""
        if employee_code in self._plans:
            del self._plans[employee_code]
            self._save()
            return True
        return False

    def get_plans_map(self) -> dict[str, SalesPlan]:
        """Get all plans as a dictionary keyed by employee code."""
        return self._plans.copy()


_repository: SalesPlansRepository | None = None


def get_sales_plans_repository() -> SalesPlansRepository:
    global _repository
    if _repository is None:
        _repository = SalesPlansRepository()
    return _repository
