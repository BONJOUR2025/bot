from __future__ import annotations

from pathlib import Path

from app.data.json_storage import JsonStorage
from app.data.salon_repository import get_salon_repository
from app.schemas.location_plan import LocationCode, LocationPlan
from app.settings import settings


class LocationRepository:
    """Stores monthly plans per location.

    The list of point codes is NOT stored here — it is derived from the
    «Салоны» page (active salons that have a code filled in), so that codes are
    managed in a single place. Plans are still keyed by salon code.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.storage = JsonStorage(path or settings.locations_file)
        self._plans: dict[str, LocationPlan] = {}   # key = "month_key|code"
        self._load()

    # ── persistence ─────────────────────────────────────────────

    def _load(self) -> None:
        data = self.storage.load()
        if not isinstance(data, dict):
            data = {}

        self._plans = {}
        for item in (data.get("plans") or []):
            if isinstance(item, dict) and item.get("location_code") and item.get("month_key"):
                lp = LocationPlan.from_dict(item)
                self._plans[self._plan_key(lp.month_key, lp.location_code)] = lp

    def _save(self) -> None:
        self.storage.save({
            "plans": [p.to_dict() for p in self._plans.values()],
        })

    @staticmethod
    def _plan_key(month_key: str, code: str) -> str:
        return f"{month_key}|{code}"

    # ── Location codes (derived from «Салоны») ───────────────────

    def list_codes(self) -> list[LocationCode]:
        """Active salons with a non-empty code, mapped to point codes."""
        salons = get_salon_repository().list_salons(status="active")
        codes: list[LocationCode] = []
        seen: set[str] = set()
        for index, salon in enumerate(salons):
            code = (salon.code or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            codes.append(LocationCode(code=code, name=salon.name, sort_order=index))
        return codes

    def get_code(self, code: str) -> LocationCode | None:
        for lc in self.list_codes():
            if lc.code == code:
                return lc
        return None

    def codes_dict(self) -> dict[str, str]:
        """Return {code: name} for all active salons with a code."""
        return {lc.code: lc.name for lc in self.list_codes()}

    # ── Monthly plans ────────────────────────────────────────────

    def list_plans(self, month_key: str) -> list[LocationPlan]:
        self._load()  # always fresh from disk (two-process setup)
        return [p for p in self._plans.values() if p.month_key == month_key]

    def get_plan(self, month_key: str, code: str) -> LocationPlan | None:
        self._load()  # always fresh from disk (two-process setup)
        return self._plans.get(self._plan_key(month_key, code))

    def upsert_plan(
        self,
        location_code: str,
        month_key: str,
        repair_plan: float = 0.0,
        cosmetics_plan: float = 0.0,
        shoes_plan: float = 0.0,
    ) -> LocationPlan:
        self._load()  # sync with disk before mutating
        key = self._plan_key(month_key, location_code)
        plan = LocationPlan(
            location_code=location_code,
            month_key=month_key,
            repair_plan=repair_plan,
            cosmetics_plan=cosmetics_plan,
            shoes_plan=shoes_plan,
        )
        self._plans[key] = plan
        self._save()
        return plan

    def plans_map(self, month_key: str) -> dict[str, LocationPlan]:
        """Return {location_code: LocationPlan} for the given month."""
        self._load()  # always reload from disk so bot process sees web-server updates
        return {p.location_code: p for p in self._plans.values() if p.month_key == month_key}


_repo: LocationRepository | None = None


def get_location_repository() -> LocationRepository:
    global _repo
    if _repo is None:
        _repo = LocationRepository()
    return _repo
