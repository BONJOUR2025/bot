from __future__ import annotations

from pathlib import Path

from app.data.json_storage import JsonStorage
from app.schemas.location_plan import LocationCode, LocationPlan
from app.settings import settings

_DEFAULT_CODES = [
    {"code": "Ц",  "name": "Цех",          "sort_order": 0},
    {"code": "П",  "name": "Пассаж",       "sort_order": 1},
    {"code": "А",  "name": "Академпарк",   "sort_order": 2},
    {"code": "М",  "name": "Меркурий",     "sort_order": 3},
    {"code": "Р",  "name": "Рио",          "sort_order": 4},
    {"code": "Оз", "name": "Озерки",       "sort_order": 5},
    {"code": "Ох", "name": "Охта-Молл",    "sort_order": 6},
]


class LocationRepository:
    """Stores location codes (editable) and monthly plans per location."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.storage = JsonStorage(path or settings.locations_file)
        self._codes: dict[str, LocationCode] = {}
        self._plans: dict[str, LocationPlan] = {}   # key = "month_key|code"
        self._load()

    # ── persistence ─────────────────────────────────────────────

    def _load(self) -> None:
        data = self.storage.load()
        if not isinstance(data, dict):
            data = {}

        codes_raw = data.get("codes") or _DEFAULT_CODES
        self._codes = {}
        for item in codes_raw:
            if isinstance(item, dict) and item.get("code"):
                lc = LocationCode.from_dict(item)
                self._codes[lc.code] = lc

        self._plans = {}
        for item in (data.get("plans") or []):
            if isinstance(item, dict) and item.get("location_code") and item.get("month_key"):
                lp = LocationPlan.from_dict(item)
                self._plans[self._plan_key(lp.month_key, lp.location_code)] = lp

    def _save(self) -> None:
        self.storage.save({
            "codes": [c.to_dict() for c in sorted(self._codes.values(), key=lambda x: x.sort_order)],
            "plans": [p.to_dict() for p in self._plans.values()],
        })

    @staticmethod
    def _plan_key(month_key: str, code: str) -> str:
        return f"{month_key}|{code}"

    # ── Location codes ───────────────────────────────────────────

    def list_codes(self) -> list[LocationCode]:
        return sorted(self._codes.values(), key=lambda x: x.sort_order)

    def get_code(self, code: str) -> LocationCode | None:
        return self._codes.get(code)

    def upsert_code(self, code: str, name: str, sort_order: int | None = None) -> LocationCode:
        existing = self._codes.get(code)
        if existing:
            existing.name = name
            if sort_order is not None:
                existing.sort_order = sort_order
            lc = existing
        else:
            lc = LocationCode(
                code=code, name=name,
                sort_order=sort_order if sort_order is not None else len(self._codes),
            )
            self._codes[code] = lc
        self._save()
        return lc

    def delete_code(self, code: str) -> bool:
        if code not in self._codes:
            return False
        del self._codes[code]
        # Also remove plans for this code
        keys_to_del = [k for k in self._plans if k.endswith(f"|{code}")]
        for k in keys_to_del:
            del self._plans[k]
        self._save()
        return True

    def codes_dict(self) -> dict[str, str]:
        """Return {code: name} for all locations."""
        return {c.code: c.name for c in self._codes.values()}

    # ── Monthly plans ────────────────────────────────────────────

    def list_plans(self, month_key: str) -> list[LocationPlan]:
        return [p for p in self._plans.values() if p.month_key == month_key]

    def get_plan(self, month_key: str, code: str) -> LocationPlan | None:
        return self._plans.get(self._plan_key(month_key, code))

    def upsert_plan(
        self,
        location_code: str,
        month_key: str,
        repair_plan: float = 0.0,
        cosmetics_plan: float = 0.0,
        shoes_plan: float = 0.0,
    ) -> LocationPlan:
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
        return {p.location_code: p for p in self._plans.values() if p.month_key == month_key}


_repo: LocationRepository | None = None


def get_location_repository() -> LocationRepository:
    global _repo
    if _repo is None:
        _repo = LocationRepository()
    return _repo
