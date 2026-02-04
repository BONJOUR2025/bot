"""Utility helpers for the bot."""

from typing import Any, Optional, Union


def is_valid_user_id(user_id: Optional[Union[str, int]]) -> bool:
    """Return True if user_id looks like a real Telegram ID."""
    if not user_id:
        return False
    uid = str(user_id)
    return uid.isdigit() and len(uid) >= 6
