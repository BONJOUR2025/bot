import json
import os
from typing import Any, Dict, List, Optional

from app.config import VISITOR_EVENTS_FILE


class VisitorEventRepository:
    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or VISITOR_EVENTS_FILE
        self._data: List[Dict[str, Any]] = self._load()
        self._counter = max(
            (int(item.get("id", 0)) for item in self._data if str(item.get("id")).isdigit()),
            default=0,
        )

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

    def list(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        salon_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        self._data = self._load()  # always fresh from disk (two-process setup)
        result = []
        for item in self._data:
            created_date = str(item.get("created_at", ""))[:10]
            if date_from and created_date < date_from:
                continue
            if date_to and created_date > date_to:
                continue
            if salon_id and str(item.get("salon_id") or "") != str(salon_id):
                continue
            result.append(item)
        result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return result

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self._data = self._load()  # sync with disk before mutating
        data["id"] = self._generate_id()
        self._data.append(data)
        self._save()
        return data


_repo: VisitorEventRepository | None = None


def get_visitor_event_repository() -> VisitorEventRepository:
    global _repo
    if _repo is None:
        _repo = VisitorEventRepository()
    return _repo
