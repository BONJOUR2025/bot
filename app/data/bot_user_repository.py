import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config import BOT_USERS_FILE


class BotUserRepository:
    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or BOT_USERS_FILE
        self._data: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(self._file):
            return {}
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self) -> None:
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def list(self) -> List[Dict[str, Any]]:
        self._data = self._load()  # always fresh from disk (two-process setup)
        result = []
        for telegram_id, item in self._data.items():
            result.append({"telegram_id": telegram_id, **item})
        result.sort(key=lambda x: x.get("last_seen", ""), reverse=True)
        return result

    def touch(
        self,
        telegram_id: int | str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> None:
        self._data = self._load()  # sync with disk before mutating
        telegram_id = str(telegram_id)
        now = datetime.utcnow().isoformat()
        record = self._data.get(telegram_id, {})
        record["username"] = username or ""
        record["first_name"] = first_name or ""
        record["last_name"] = last_name or ""
        record["last_seen"] = now
        record.setdefault("first_seen", now)
        self._data[telegram_id] = record
        self._save()


_repo: BotUserRepository | None = None


def get_bot_user_repository() -> BotUserRepository:
    global _repo
    if _repo is None:
        _repo = BotUserRepository()
    return _repo
