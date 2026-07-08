from __future__ import annotations

from datetime import datetime
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

    def get_by_order_code(self, order_code: str) -> Salon | None:
        """Look up a salon by its Firebird order-number suffix code.

        No status filter — a closed/renovation salon must still resolve so
        historical payroll-by-salon reports keep attributing correctly.
        """
        self._load()  # always fresh from disk (two-process setup)
        order_code = (order_code or "").strip()
        if not order_code:
            return None
        for salon in self._salons.values():
            if (salon.order_code or "").strip() == order_code:
                return salon
        return None

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
