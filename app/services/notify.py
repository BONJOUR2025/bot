"""Send plain-text notifications to the configured notification_chat_id."""
import logging
import httpx

log = logging.getLogger(__name__)


async def send_secretary_message(chat_id: str | int, text: str) -> str | None:
    """
    Send a message from the owner's personal Telegram via Secretary Mode.
    Returns None on success, or an error string describing the failure.
    """
    try:
        from app.services.config_service import ConfigService
        cfg = ConfigService().load()
        connection_id = str(cfg.get("tg_business_connection_id") or "").strip()
        can_reply = cfg.get("tg_business_can_reply", False)

        if not connection_id:
            return "Secretary Mode не подключён. Перейдите в Telegram → Настройки → Chat Automation и подключите бота."
        if not can_reply:
            return "Secretary Mode подключён, но без права отвечать (can_reply=false). Переподключите бота с разрешением отвечать."

        from app.config import TOKEN
        if not TOKEN:
            return "Telegram bot token не настроен."

        from app.settings import settings
        proxy = getattr(settings, "telegram_proxy", None)
        client_kwargs: dict = {"timeout": 10.0}
        if proxy:
            client_kwargs["proxy"] = proxy

        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": int(chat_id),
            "text": text,
            "parse_mode": "HTML",
            "business_connection_id": connection_id,
        }

        async with httpx.AsyncClient(**client_kwargs) as client:
            r = await client.post(url, json=payload)

        if r.status_code == 200:
            log.info("Secretary message sent to chat_id=%s", chat_id)
            return None

        data = r.json() if r.content else {}
        description = data.get("description") or r.text[:200]
        log.warning("Secretary message failed chat_id=%s: HTTP %s — %s", chat_id, r.status_code, description)
        return f"Telegram: {description}"

    except Exception as exc:
        log.warning("send_secretary_message error: %s", exc)
        return f"Ошибка отправки в Telegram: {exc}"


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
