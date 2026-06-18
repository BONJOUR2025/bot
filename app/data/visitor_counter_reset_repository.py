import json
import os
from typing import Dict, Optional

from app.config import VISITOR_COUNTER_RESETS_FILE


class VisitorCounterResetRepository:
    """Maps salon_id -> ISO timestamp of the last counter reset for that salon."""

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or VISITOR_COUNTER_RESETS_FILE

    def _load(self) -> Dict[str, str]:
        if not os.path.exists(self._file):
            return {}
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self, data: Dict[str, str]) -> None:
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get(self, salon_id: str) -> Optional[str]:
        return self._load().get(salon_id)

    def set(self, salon_id: str, timestamp: str) -> None:
        data = self._load()
        data[salon_id] = timestamp
        self._save(data)


_repo: VisitorCounterResetRepository | None = None


def get_visitor_counter_reset_repository() -> VisitorCounterResetRepository:
    global _repo
    if _repo is None:
        _repo = VisitorCounterResetRepository()
    return _repo
