import json
import os
from typing import List, Dict, Any, Optional

from app.config import LEAVE_REQUESTS_FILE
from app.utils.logger import log


class LeaveRequestRepository:
    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or LEAVE_REQUESTS_FILE
        self._data: List[Dict[str, Any]] = self._load()
        self._counter = max(
            (int(r.get("id", 0)) for r in self._data if str(r.get("id")).isdigit()),
            default=0,
        )

    def _load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self._file):
            return []
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"❌ Failed reading {self._file}: {e}")
            return []

    def _save(self) -> None:
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _generate_id(self) -> int:
        self._counter += 1
        return self._counter

    def list(self, employee_id: Optional[str] = None) -> List[Dict[str, Any]]:
        result = self._data
        if employee_id:
            result = [r for r in result if str(r.get("employee_id")) == str(employee_id)]
        return sorted(result, key=lambda r: r.get("created_at", ""), reverse=True)

    def get(self, request_id: str) -> Optional[Dict[str, Any]]:
        for item in self._data:
            if str(item.get("id")) == str(request_id):
                return item
        return None

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        data["id"] = self._generate_id()
        self._data.append(data)
        self._save()
        return data

    def update(self, request_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for item in self._data:
            if str(item.get("id")) == str(request_id):
                item.update(updates)
                self._save()
                return item
        return None

    def delete(self, request_id: str) -> None:
        self._data = [r for r in self._data if str(r.get("id")) != str(request_id)]
        self._save()
