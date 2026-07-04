"""Minimal VK API client for sending a message to a VK user — used from
BOTH processes (the VK bot itself, and the Telegram/admin process notifying
a VK-linked employee of a decision made in Telegram/the web admin). This is
a plain HTTP call (VK's messages.send method), independent of vkbottle's
running Bot/Long Poll connection, so it works even from a process that
isn't the VK bot itself.
"""

from __future__ import annotations

import random
from typing import Optional

import httpx

from app.settings import settings
from app.utils.logger import log

VK_API_BASE = "https://api.vk.com/method"
VK_API_VERSION = "5.199"


def is_configured() -> bool:
    return bool(settings.vk_api_token)


async def send_message(vk_id: int | str, text: str) -> Optional[int]:
    """Send a plain text message to a VK user. Returns the message id, or
    None if VK isn't configured or the send failed (never raises — callers
    treat a notification failure as non-fatal, same as the Telegram side)."""
    if not is_configured():
        log("⚠️ [vk_client] VK_API_TOKEN не задан — сообщение не отправлено")
        return None
    params = {
        "access_token": settings.vk_api_token,
        "v": VK_API_VERSION,
        "user_id": str(vk_id),
        "message": text,
        "random_id": random.randint(1, 2_147_483_647),
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{VK_API_BASE}/messages.send", data=params)
            data = resp.json()
        if "error" in data:
            log(f"❌ [vk_client] Ошибка отправки сообщения {vk_id}: {data['error']}")
            return None
        return data.get("response")
    except Exception as exc:
        log(f"❌ [vk_client] Не удалось отправить сообщение {vk_id}: {exc}")
        return None
