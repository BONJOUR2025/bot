from typing import List, Optional

from app.schemas.incentive import Incentive, IncentiveCreate, IncentiveUpdate
from app.data.incentive_repository import IncentiveRepository


class IncentiveService:
    def __init__(self, repo: Optional[IncentiveRepository] = None) -> None:
        self._repo = repo or IncentiveRepository()

    async def list_incentives(
        self,
        employee_id: Optional[str] = None,
        typ: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Incentive]:
        rows = self._repo.list(employee_id, typ, date_from, date_to)
        return [Incentive(**r) for r in rows]

    async def create_incentive(self, data: IncentiveCreate) -> Incentive:
        created = self._repo.create(data.model_dump())
        return Incentive(**created)

    async def update_incentive(self, item_id: str, data: IncentiveUpdate) -> Optional[Incentive]:
        updated = self._repo.update(item_id, data.model_dump(exclude_none=True))
        return Incentive(**updated) if updated else None

    async def delete_incentive(self, item_id: str) -> bool:
        return self._repo.delete(item_id)
