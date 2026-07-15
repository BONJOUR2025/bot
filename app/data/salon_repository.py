from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from app.data.json_storage import JsonStorage
from app.schemas.salon import Salon, SalonCreate, SalonUpdate, new_salon
from app.settings import settings


class SalonRepository:
    def __init__(self, path: str | Path | None = None) -> None:
        self.storage = JsonStorage(path or settings.salons_file)
        self._salons: dict[str, Salon] = {}
        self._load()

    def _load(self) -> None:
        data = self.storage.load()
        self._salons = {}
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("id"):
                    salon = Salon.from_dict(item)
                    self._salons[salon.id] = salon

    def _save(self) -> None:
        self.storage.save([s.to_dict() for s in self._salons.values()])

    def list_salons(self, status: str | None = None) -> list[Salon]:
        self._load()  # always fresh from disk (two-process setup)
        salons = list(self._salons.values())
        if status:
            salons = [s for s in salons if s.status == status]
        return sorted(salons, key=lambda s: s.name)

    def get(self, salon_id: str) -> Salon | None:
        self._load()  # always fresh from disk (two-process setup)
        return self._salons.get(salon_id)

    def get_by_code(self, code: str) -> Salon | None:
        self._load()  # always fresh from disk (two-process setup)
        code = (code or "").strip().lower()
        if not code:
            return None
        for salon in self._salons.values():
            if (salon.code or "").strip().lower() == code:
                return salon
        return None

    @staticmethod
    def _disambiguate_by_opening_date(
        candidates: list[Salon], year: int | None, month: int | None
    ) -> Salon | None:
        """Pick the one candidate whose opening_date fits a target month.

        Shared by get_by_order_code and get_by_sclad_id: a physical point
        can be renamed/moved (e.g. "Пассаж" -> "Гранд Палас") while keeping
        the same Firebird order-number suffix AND the same Agbis SCLAD, so
        two `Salon` records can legitimately share one order_code or
        sclad_id. When that happens and a target month is given,
        disambiguate by `opening_date`: pick the record whose opening_date
        is the most recent one that had already passed by the target month
        (a record with no opening_date is treated as "always open", i.e.
        the oldest possible start). If nothing resolves that way (or no
        month was given), fall back to the first match for backward
        compatibility.
        """
        if not candidates:
            return None
        if len(candidates) == 1 or year is None or month is None:
            return candidates[0]

        def _effective_start(s: Salon) -> date:
            if not s.opening_date:
                return date.min
            try:
                return date.fromisoformat(s.opening_date)
            except ValueError:
                return date.min

        target = date(year, month, 1)
        eligible = [s for s in candidates if _effective_start(s) <= target]
        if not eligible:
            # Every candidate's opening_date is after the target month —
            # none of them existed yet, so don't guess.
            return None
        eligible.sort(key=_effective_start)
        winner_start = _effective_start(eligible[-1])
        if sum(1 for s in eligible if _effective_start(s) == winner_start) > 1:
            # Two+ records tie for the most recent start (typically both
            # missing opening_date) — no way to tell which is right for
            # this month, so don't silently guess.
            return None
        return eligible[-1]

    def get_by_order_code(
        self, order_code: str, year: int | None = None, month: int | None = None
    ) -> Salon | None:
        """Look up a salon by its Firebird order-number suffix code.

        No status filter — a closed/renovation salon must still resolve so
        historical payroll-by-salon reports keep attributing correctly.
        See _disambiguate_by_opening_date for the same-code tie-break.
        """
        self._load()  # always fresh from disk (two-process setup)
        order_code = (order_code or "").strip()
        if not order_code:
            return None
        candidates = [
            s for s in self._salons.values()
            if (s.order_code or "").strip() == order_code
        ]
        return self._disambiguate_by_opening_date(candidates, year, month)

    def get_by_sclad_id(
        self, sclad_id: int, year: int | None = None, month: int | None = None
    ) -> Salon | None:
        """Look up a salon by an Agbis SCLADS.ID bound via the Salons page.

        See _disambiguate_by_opening_date for the same-sclad tie-break
        (e.g. "Пассаж" and "Гранд Палас" share one physical SCLAD).
        """
        self._load()  # always fresh from disk (two-process setup)
        candidates = [
            s for s in self._salons.values()
            if sclad_id in (s.sclad_ids or [])
        ]
        return self._disambiguate_by_opening_date(candidates, year, month)

    def create(self, data: SalonCreate) -> Salon:
        self._load()  # sync with disk before mutating
        salon = new_salon(data)
        self._salons[salon.id] = salon
        self._save()
        return salon

    def update(self, salon_id: str, data: SalonUpdate) -> Salon | None:
        self._load()  # sync with disk before mutating
        salon = self._salons.get(salon_id)
        if not salon:
            return None
        patch = data.dict(exclude_none=True)
        updated = salon.dict()
        updated.update(patch)
        updated["updated_at"] = datetime.utcnow().isoformat()
        self._salons[salon_id] = Salon.from_dict(updated)
        self._save()
        return self._salons[salon_id]

    def delete(self, salon_id: str) -> bool:
        self._load()  # sync with disk before mutating
        if salon_id not in self._salons:
            return False
        del self._salons[salon_id]
        self._save()
        return True


_repo: SalonRepository | None = None


def get_salon_repository() -> SalonRepository:
    global _repo
    if _repo is None:
        _repo = SalonRepository()
    return _repo
