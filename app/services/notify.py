"""Send plain-text notifications to the configured notification_chat_id."""
import logging
import httpx

log = logging.getLogger(__name__)


async def send_notification(text: str) -> bool:
    """Send text to notification_chat_id from config. Returns True on success, never raises."""
    try:
        from app.services.config_service import ConfigService
        chat_id = str(ConfigService().load().get("notification_chat_id") or "").strip()
        if not chat_id:
            log.debug("send_notification: notification_chat_id not configured, skipping")
            return False

        from app.config import TOKEN
        if not TOKEN:
            log.warning("send_notification: telegram bot token not configured")
            return False

        from app.settings import settings
        proxy = getattr(settings, "telegram_proxy", None)

        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": int(chat_id), "text": text, "parse_mode": "HTML"}

        client_kwargs = {"timeout": 10.0}
        if proxy:
            client_kwargs["proxy"] = proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            r = await client.post(url, json=payload)

        if r.status_code == 200:
            log.info("Notification sent to chat_id=%s", chat_id)
            return True
        else:
            log.warning("Notification failed: HTTP %s — %s", r.status_code, r.text[:200])
            return False

    except Exception as exc:
        log.warning("send_notification error: %s", exc)
        return False
