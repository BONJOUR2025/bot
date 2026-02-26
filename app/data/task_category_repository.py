import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

DEFAULT_FILE = "task_categories.json"


class TaskCategoryRepository:
    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or DEFAULT_FILE
        self._data: List[Dict[str, Any]] = self._load()
        self._counter = max((int(c["id"]) for c in self._data if c.get("id")), default=0)

    def _load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self._file):
            return []
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for c in data:
                if "id" in c:
                    c["id"] = int(c["id"])
            return data
        except Exception:
            return []

    def _save(self) -> None:
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def list(self) -> List[Dict[str, Any]]:
        return list(self._data)

    def get(self, cat_id: int) -> Optional[Dict[str, Any]]:
        for c in self._data:
            if c.get("id") == cat_id:
                return c
        return None

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self._counter += 1
        data["id"] = self._counter
        data["created_at"] = datetime.now().isoformat()
        self._data.append(data)
        self._save()
        return data

    def update(self, cat_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for c in self._data:
            if c.get("id") == cat_id:
                c.update({k: v for k, v in updates.items() if v is not None})
                c["updated_at"] = datetime.now().isoformat()
                self._save()
                return c
        return None

    def delete(self, cat_id: int) -> bool:
        before = len(self._data)
        self._data = [c for c in self._data if c.get("id") != cat_id]
        if len(self._data) != before:
            self._save()
            return True
        return False
