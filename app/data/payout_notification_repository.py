"""Repository for the payout notification journal.

Records every notification the system tries to send to an employee when a
payout changes status (approved / rejected / paid): the recipient, the exact
message text, the channel and the *real* delivery result. Surfaced in the
admin UI so approvals are no longer invisible there.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.settings import settings

DEFAULT_FILE = "payout_notifications.json"
MAX_ENTRIES = 2000  # keep the journal bounded


class PayoutNotificationRepository:
    """Stores payout notification journal entries in a JSON file."""

    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file = Path(
            file_path or getattr(settings, "payout_notifications_file", DEFAULT_FILE)
        )
        self._data: list[dict[str, Any]] = self._load()

    def _load(self) -> list[dict[str, Any]]:
        if not self._file.exists():
            return []
        try:
            with open(self._file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self) -> None:
        try:
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_entry(
        self,
        *,
        payout_id: Any,
        user_id: str,
        recipient_name: str,
        status: str,
        channel: str,
        message: str,
        delivery: str,
        error: str | None = None,
        amount: Any = None,
    ) -> dict[str, Any]:
        entry = {
            "id": len(self._data) + 1,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "payout_id": payout_id,
            "user_id": user_id,
            "recipient_name": recipient_name,
            "status": status,
            "channel": channel,        # "telegram" | "push"
            "message": message,
            "delivery": delivery,      # "sent" | "failed" | "skipped"
            "error": error,
            "amount": amount,
        }
        self._data.append(entry)
        if len(self._data) > MAX_ENTRIES:
            self._data = self._data[-MAX_ENTRIES:]
        self._save()
        return entry

    def get_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        # Most recent first.
        return list(reversed(self._data))[:limit]


_repo: PayoutNotificationRepository | None = None


def get_payout_notification_repository() -> PayoutNotificationRepository:
    global _repo
    if _repo is None:
        _repo = PayoutNotificationRepository()
    return _repo
