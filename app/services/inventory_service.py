from typing import Optional

from app.data.asset_repository import AssetRepository
from app.data.inventory_repository import InventoryRepository


class InventoryService:
    def __init__(
        self,
        inventory_repo: Optional[InventoryRepository] = None,
        asset_repo: Optional[AssetRepository] = None,
    ) -> None:
        self._inventory_repo = inventory_repo or InventoryRepository()
        self._asset_repo = asset_repo or AssetRepository()

    async def available(self, item_name: str, size: Optional[str] = None) -> int:
        total = self._inventory_repo.get_quantity(item_name, size)
        issued = sum(
            a.get("quantity", 0)
            for a in self._asset_repo.list()
            if a.get("item_name") == item_name
            and (size is None or a.get("size") == size)
            and not a.get("return_date")
        )
        free = total - issued
        return free if free > 0 else 0
