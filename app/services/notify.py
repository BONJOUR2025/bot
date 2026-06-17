"""Send plain-text notifications to the configured notification_chat_id."""
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

# Secretary Mode (Telegram Business Connection) can silently drop — e.g. the
# owner's phone/Telegram session goes offline over a weekend — and Telegram
# pushes a business_connection update with is_enabled=False, which clears
# tg_business_connection_id/tg_business_can_reply (see handle_business_connection).
# Both the AI interview and the follow-up job route every candidate message
# through send_secretary_message, and previously just logged a warning on the
# early-return below — so neither feature appeared to "work" with no visible
# cause. Alert the admin (rate-limited so a burst of candidate messages doesn't
# spam them) so they know to reconnect Chat Automation.
_DISCONNECT_ALERT_COOLDOWN = timedelta(hours=1)
_last_disconnect_alert: datetime | None = None


async def _alert_secretary_disconnected(reason: str) -> None:
    global _last_disconnect_alert
    now = datetime.utcnow()
    if _last_disconnect_alert and (now - _last_disconnect_alert) < _DISCONNECT_ALERT_COOLDOWN:
        return
    _last_disconnect_alert = now
    try:
        await send_notification(
            f"⚠️ <b>Secretary Mode отключён</b>\n{reason}\n\n"
            f"Пока бот не переподключён, ИИ-ассистент и напоминания кандидатам "
            f"работать не будут — переподключите Chat Automation в настройках Telegram."
        )
    except Exception as exc:
        log.warning("Failed to alert admin about Secretary Mode disconnect: %s", exc)


async def send_secretary_message(chat_id: str | int, text: str) -> str | None:
    """
    Send a message from the owner's personal Telegram via Secretary Mode.
    Retries up to 2 more times on failure. If all 3 attempts fail, alerts admin.
    Returns None on success, or an error string describing the failure.
    """
    try:
        from app.services.config_service import ConfigService
        cfg = ConfigService().load()
        connection_id = str(cfg.get("tg_business_connection_id") or "").strip()
        can_reply = cfg.get("tg_business_can_reply", False)

        if not connection_id:
            await _alert_secretary_disconnected(
                "Подключение Chat Automation не найдено (tg_business_connection_id пуст)."
            )
            return "Secretary Mode не подключён. Перейдите в Telegram → Настройки → Chat Automation и подключите бота."
        if not can_reply:
            await _alert_secretary_disconnected(
                "Подключение есть, но бот не может отвечать (can_reply=false)."
            )
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

        last_description = ""
        for attempt in range(3):
            if attempt > 0:
                await asyncio.sleep(2)
            try:
                async with httpx.AsyncClient(**client_kwargs) as client:
                    r = await client.post(url, json=payload)

                if r.status_code == 200:
                    log.info("Secretary message sent to chat_id=%s (attempt %d)", chat_id, attempt + 1)
                    return None

                data = r.json() if r.content else {}
                last_description = data.get("description") or r.text[:200]
                log.warning("Secretary message failed chat_id=%s attempt %d: HTTP %s — %s",
                            chat_id, attempt + 1, r.status_code, last_description)
            except Exception as exc:
                last_description = str(exc)
                log.warning("send_secretary_message error attempt %d: %s", attempt + 1, exc)

        # All 3 attempts failed — alert admin
        error_str = f"Telegram: {last_description}"
        try:
            await send_notification(
                f"❌ Сообщение не доставлено кандидату\n"
                f"chat_id: {chat_id}\n"
                f"Текст: {text[:100]}...\n"
                f"Ошибка: {last_description}"
            )
        except Exception as notify_exc:
            log.warning("Failed to send admin alert for secretary failure: %s", notify_exc)
        return error_str

    except Exception as exc:
        log.warning("send_secretary_message error: %s", exc)
        return f"Ошибка отправки в Telegram: {exc}"


async def send_notification_with_keyboard(text: str, buttons: list) -> bool:
    """Send notification with inline keyboard. buttons = [[{"text":"..","callback_data":".."}]]"""
    try:
        from app.services.config_service import ConfigService
        chat_id = str(ConfigService().load().get("notification_chat_id") or "").strip()
        if not chat_id:
            return False
        from app.config import TOKEN
        if not TOKEN:
            return False
        from app.settings import settings
        proxy = getattr(settings, "telegram_proxy", None)
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": int(chat_id),
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": buttons},
        }
        client_kwargs = {"timeout": 10.0}
        if proxy:
            client_kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**client_kwargs) as client:
            r = await client.post(url, json=payload)
        return r.status_code == 200
    except Exception as exc:
        log.warning("send_notification_with_keyboard error: %s", exc)
        return False


async def send_chat_message(
    chat_id: str | int, text: str, parse_mode: str = "Markdown", reply_markup: dict | None = None
) -> bool:
    """Send a plain message to an arbitrary chat_id (not tied to any config key).
    Returns True on success, never raises."""
    try:
        from app.config import TOKEN
        if not TOKEN:
            log.warning("send_chat_message: telegram bot token not configured")
            return False

        from app.settings import settings
        proxy = getattr(settings, "telegram_proxy", None)

        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": int(chat_id), "text": text, "parse_mode": parse_mode}
        if reply_markup:
            payload["reply_markup"] = reply_markup

        client_kwargs: dict = {"timeout": 10.0}
        if proxy:
            client_kwargs["proxy"] = proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            r = await client.post(url, json=payload)

        if r.status_code == 200:
            return True
        log.warning("send_chat_message failed chat_id=%s: HTTP %s — %s", chat_id, r.status_code, r.text[:200])
        return False
    except Exception as exc:
        log.warning("send_chat_message error: %s", exc)
        return False


async def send_chat_document(
    chat_id: str | int,
    file_path: str,
    caption: str = "",
    parse_mode: str = "Markdown",
    reply_markup: dict | None = None,
) -> bool:
    """Send a file already on disk as a Telegram document to an arbitrary chat_id."""
    try:
        from app.config import TOKEN
        if not TOKEN:
            log.warning("send_chat_document: telegram bot token not configured")
            return False
        if not Path(file_path).exists():
            log.warning("send_chat_document: file not found: %s", file_path)
            return False

        from app.settings import settings
        proxy = getattr(settings, "telegram_proxy", None)

        url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"
        data: dict = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = parse_mode
        if reply_markup:
            import json as _json
            data["reply_markup"] = _json.dumps(reply_markup)

        client_kwargs: dict = {"timeout": 30.0}
        if proxy:
            client_kwargs["proxy"] = proxy

        with open(file_path, "rb") as f:
            files = {"document": (Path(file_path).name, f)}
            async with httpx.AsyncClient(**client_kwargs) as client:
                r = await client.post(url, data=data, files=files)

        if r.status_code == 200:
            return True
        log.warning("send_chat_document failed chat_id=%s: HTTP %s — %s", chat_id, r.status_code, r.text[:200])
        return False
    except Exception as exc:
        log.warning("send_chat_document error: %s", exc)
        return False


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
