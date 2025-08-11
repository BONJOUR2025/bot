import json
from pathlib import Path
from typing import Any, Dict, List

from app.data.employee_repository import EmployeeRepository
from app.data.payout_repository import PayoutRepository
from app.data.vacation_repository import VacationRepository
from app.data.incentive_repository import IncentiveRepository
from app.data.asset_repository import AssetRepository
from app.core.enums import EmployeeStatus, PAYOUT_STATUSES
from app.core.constants import PAYOUT_METHODS, PAYOUT_TYPES


class DictionaryService:
    """Load and save dropdown dictionary values."""

    def __init__(self, path: str | Path = "dictionary.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _collect_defaults(self) -> Dict[str, List[str]]:
        """Return predefined dictionary values from code constants."""
        return {
            "employee_statuses": [s.value for s in EmployeeStatus],
            "payout_methods": PAYOUT_METHODS,
            "payout_types": PAYOUT_TYPES,
            "payout_statuses": PAYOUT_STATUSES,
        }

    def _collect_dynamic(self) -> Dict[str, List[str]]:
        """Gather unique values from existing system records."""
        dynamic: Dict[str, List[str]] = {}

        employees = EmployeeRepository().list_employees()
        dynamic["positions"] = [e.position for e in employees if e.position]
        dynamic["work_places"] = [
            getattr(e, "work_place", "") for e in employees if getattr(e, "work_place", "")
        ]
        dynamic["employee_statuses"] = [e.status.value for e in employees]

        payouts = PayoutRepository().load_all()
        dynamic["payout_types"] = [
            p.get("payout_type") for p in payouts if p.get("payout_type")
        ]
        dynamic["payout_methods"] = [
            p.get("method") for p in payouts if p.get("method")
        ]
        dynamic["payout_statuses"] = [
            p.get("status") for p in payouts if p.get("status")
        ]

        vacations = VacationRepository().list()
        dynamic["vacation_types"] = [v.get("type") for v in vacations if v.get("type")]

        incentives = IncentiveRepository().list()
        dynamic["incentive_types"] = [
            i.get("type") for i in incentives if i.get("type")
        ]

        assets = AssetRepository().list()
        dynamic["asset_items"] = [
            a.get("item_name") for a in assets if a.get("item_name")
        ]
        dynamic["asset_sizes"] = [a.get("size") for a in assets if a.get("size")]


        return dynamic

    def load(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        dynamic = self._collect_dynamic()
        defaults = self._collect_defaults()
        for key in set(dynamic) | set(defaults):
            existing = set(data.get(key, []))
            existing.update([v for v in dynamic.get(key, []) if v])
            existing.update([v for v in defaults.get(key, []) if v])
            if existing:
                data[key] = sorted(existing)

        return data

    def save(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data

    def patch(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        current = self.load()
        current.update(updates)
        return self.save(current)
