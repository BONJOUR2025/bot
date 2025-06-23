from typing import List, Optional

from app.schemas.vacation import Vacation, VacationCreate, VacationUpdate
from app.data.vacation_repository import VacationRepository


class VacationService:
    def __init__(self, repo: Optional[VacationRepository] = None) -> None:
        self._repo = repo or VacationRepository()

    async def list_vacations(self) -> List[Vacation]:
        rows = self._repo.list()
        return [Vacation(**r) for r in rows]

    async def create_vacation(self, data: VacationCreate) -> Vacation:
        created = self._repo.create(data.model_dump())
        return Vacation(**created)

    async def update_vacation(
            self,
            vac_id: str,
            data: VacationUpdate) -> Optional[Vacation]:
        updated = self._repo.update(vac_id, data.model_dump(exclude_none=True))
        return Vacation(**updated) if updated else None

    async def delete_vacation(self, vac_id: str) -> None:
        self._repo.delete(vac_id)
