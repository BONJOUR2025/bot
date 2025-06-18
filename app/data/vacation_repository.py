import json
import os
from typing import List, Dict, Any, Optional

from app.config import VACATIONS_FILE


class VacationRepository:
    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or VACATIONS_FILE
        self._data: List[Dict[str, Any]] = self._load()
        self._counter = max(
            (int(
                v.get(
                    "id",
                    0)) for v in self._data if str(
                v.get("id")).isdigit()),
            default=0)

    def _load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self._file):
            return []
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self) -> None:
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _generate_id(self) -> int:
        self._counter += 1
        return self._counter

    def list(self) -> List[Dict[str, Any]]:
        return list(self._data)

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if "id" not in data or any(
                str(v.get("id")) == str(data["id"]) for v in self._data):
            data["id"] = self._generate_id()
        self._data.append(data)
        self._save()
        return data

    def update(self, vac_id: str,
               updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for item in self._data:
            if str(item.get("id")) == str(vac_id):
                item.update(
                    {k: v for k, v in updates.items() if v is not None})
                self._save()
                return item
        return None

    def delete(self, vac_id: str) -> None:
        self._data = [v for v in self._data if str(v.get("id")) != str(vac_id)]
        self._save()
