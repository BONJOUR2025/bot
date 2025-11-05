from typing import List, Optional

from app.schemas.asset import Asset, AssetCreate, AssetUpdate
from app.data.asset_repository import AssetRepository


class AssetService:
    def __init__(self, repo: Optional[AssetRepository] = None) -> None:
        self._repo = repo or AssetRepository()

    async def list_assets(self, employee_id: Optional[str] = None) -> List[Asset]:
        rows = self._repo.list(employee_id)
        return [Asset(**r) for r in rows]

    async def create_asset(self, data: AssetCreate) -> Asset:
        created = self._repo.create(data.model_dump())
        return Asset(**created)

    async def update_asset(self, item_id: str, data: AssetUpdate) -> Optional[Asset]:
        updated = self._repo.update(item_id, data.model_dump(exclude_none=True))
        return Asset(**updated) if updated else None

    async def delete_asset(self, item_id: str) -> None:
        self._repo.delete(item_id)

    def get_asset_employee(self, item_id: str) -> Optional[str]:
        for item in self._repo.list():
            if str(item.get("id")) == str(item_id):
                employee_id = item.get("employee_id")
                return str(employee_id) if employee_id is not None else None
        return None
