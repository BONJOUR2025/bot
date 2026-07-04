import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config import VK_BOT_USERS_FILE


class VkBotUserRepository:
    """Raw log of everyone who has ever messaged the (future) VK bot —
    mirrors BotUserRepository (Telegram) so the same admin-linking flow can
    be reused once a VK bot exists. touch() is meant to be called from the
    VK bot's message/start handler, the same way start.py calls the
    Telegram version today."""

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or VK_BOT_USERS_FILE
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
        for vk_id, item in self._data.items():
            result.append({"vk_id": vk_id, **item})
        result.sort(key=lambda x: x.get("last_seen", ""), reverse=True)
        return result

    def touch(
        self,
        vk_id: int | str,
        screen_name: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> None:
        self._data = self._load()  # sync with disk before mutating
        vk_id = str(vk_id)
        now = datetime.utcnow().isoformat()
        record = self._data.get(vk_id, {})
        record["screen_name"] = screen_name or ""
        record["first_name"] = first_name or ""
        record["last_name"] = last_name or ""
        record["last_seen"] = now
        record.setdefault("first_seen", now)
        self._data[vk_id] = record
        self._save()


_repo: VkBotUserRepository | None = None


def get_vk_bot_user_repository() -> VkBotUserRepository:
    global _repo
    if _repo is None:
        _repo = VkBotUserRepository()
    return _repo
