import json
import os
from typing import Any, Dict, List, Optional

from app.config import INVENTORY_FILE
from app.utils.logger import log


class InventoryRepository:
    """Simple JSON-backed storage for inventory totals."""

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or INVENTORY_FILE
        log(f"\U0001F4C2 Loading inventory from {self._file}")
        self._data: List[Dict[str, Any]] = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self._file):
            example = self._file.replace('.json', '.example.json')
            if os.path.exists(example):
                try:
                    with open(example, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    with open(self._file, 'w', encoding='utf-8') as out:
                        json.dump(data, out, ensure_ascii=False, indent=2)
                    return data
                except Exception as e:
                    log(f"\u274C Failed reading example {example}: {e}")
                    return []
            log(f"\u274C {self._file} not found and no example")
            return []
        try:
            with open(self._file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log(f"\u274C Failed reading {self._file}: {e}")
            return []

    def list(self) -> List[Dict[str, Any]]:
        return list(self._data)

    def get_quantity(self, item_name: str, size: Optional[str] = None) -> int:
        for item in self._data:
            if item.get('item_name') == item_name and (size is None or item.get('size') == size):
                return int(item.get('quantity', 0))
        return 0
