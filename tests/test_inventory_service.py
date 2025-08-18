import json
import os
import sys
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.inventory_service import InventoryService
from app.data.inventory_repository import InventoryRepository
from app.data.asset_repository import AssetRepository


def test_available_calculation(tmp_path):
    inv_path = tmp_path / "inventory.json"
    asset_path = tmp_path / "assets.json"
    inv_path.write_text(
        json.dumps([
            {"item_name": "Фартук", "size": "Универсальный", "quantity": 10}
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    asset_path.write_text(
        json.dumps(
            [
                {
                    "employee_id": "1",
                    "employee_name": "Test",
                    "position": "",
                    "item_name": "Фартук",
                    "size": "Универсальный",
                    "quantity": 3,
                    "issue_date": "2025-01-01",
                    "return_date": "",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    inv_repo = InventoryRepository(str(inv_path))
    asset_repo = AssetRepository(str(asset_path))
    service = InventoryService(inv_repo, asset_repo)
    free = asyncio.run(service.available("Фартук", "Универсальный"))
    assert free == 7
