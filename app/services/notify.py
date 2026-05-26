"""Send plain-text notifications to the configured notification_chat_id."""
import logging

log = logging.getLogger(__name__)


async def send_notification(text: str) -> bool:
    """Send text to notification_chat_id from config. Returns True on success, never raises."""
    try:
        from app.services.config_service import ConfigService
        chat_id = ConfigService().load().get("notification_chat_id", "")
        if not chat_id:
            return False
        from app.config import TOKEN
        if not TOKEN:
            return False
        from telegram import Bot
        from telegram.request import HTTPXRequest
        from app.settings import settings
        req = HTTPXRequest(proxy=settings.telegram_proxy) if getattr(settings, "telegram_proxy", None) else HTTPXRequest()
        async with Bot(token=TOKEN, request=req) as bot:
            await bot.send_message(chat_id=int(chat_id), text=text, parse_mode="HTML")
        return True
    except Exception as exc:
        log.warning("Notification send failed: %s", exc)
        return False
