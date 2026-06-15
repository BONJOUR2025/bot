import json
import os
from typing import Any, Dict, List, Optional

from app.config import SHIFT_CHECKINS_FILE


class ShiftCheckinRepository:
    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or SHIFT_CHECKINS_FILE
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
        employee_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        result = []
        for item in self._data:
            if date_from and str(item.get("date", "")) < date_from:
                continue
            if date_to and str(item.get("date", "")) > date_to:
                continue
            if salon_id and str(item.get("salon_id") or "") != str(salon_id):
                continue
            if employee_id and str(item.get("employee_id") or "") != str(employee_id):
                continue
            result.append(item)
        result.sort(key=lambda x: x.get("sent_at", ""), reverse=True)
        return result

    def get(self, checkin_id: int) -> Optional[Dict[str, Any]]:
        for item in self._data:
            if int(item.get("id", 0)) == int(checkin_id):
                return item
        return None

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        data["id"] = self._generate_id()
        self._data.append(data)
        self._save()
        return data

    def update(self, checkin_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for item in self._data:
            if int(item.get("id", 0)) == int(checkin_id):
                item.update(updates)
                self._save()
                return item
        return None


_repo: ShiftCheckinRepository | None = None


def get_shift_checkin_repository() -> ShiftCheckinRepository:
    global _repo
    if _repo is None:
        _repo = ShiftCheckinRepository()
    return _repo
