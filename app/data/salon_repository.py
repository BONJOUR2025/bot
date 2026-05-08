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
        salons = list(self._salons.values())
        if status:
            salons = [s for s in salons if s.status == status]
        return sorted(salons, key=lambda s: s.name)

    def get(self, salon_id: str) -> Salon | None:
        return self._salons.get(salon_id)

    def create(self, data: SalonCreate) -> Salon:
        salon = new_salon(data)
        self._salons[salon.id] = salon
        self._save()
        return salon

    def update(self, salon_id: str, data: SalonUpdate) -> Salon | None:
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
