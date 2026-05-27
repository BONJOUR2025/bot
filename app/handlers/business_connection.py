"""Handle Telegram Secretary Mode (Chat Automation) business_connection updates."""
import logging

log = logging.getLogger(__name__)


async def handle_business_connection(update, context):
    """Save/remove business_connection_id when user connects/disconnects the bot."""
    conn = update.business_connection
    if not conn:
        return

    from app.services.config_service import ConfigService
    svc = ConfigService()

    if conn.is_enabled:
        svc.patch({
            "tg_business_connection_id": conn.id,
            "tg_business_user_id": conn.user_id,
            "tg_business_can_reply": conn.can_reply,
        })
        log.info("Secretary Mode connected: user_id=%s connection_id=%s can_reply=%s",
                 conn.user_id, conn.id, conn.can_reply)
    else:
        svc.patch({
            "tg_business_connection_id": "",
            "tg_business_user_id": None,
            "tg_business_can_reply": False,
        })
        log.info("Secretary Mode disconnected: user_id=%s", conn.user_id)
