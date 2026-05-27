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


async def handle_business_message(update, context):
    """Save incoming messages from candidates to DB."""
    msg = update.business_message
    if not msg or not msg.text:
        return

    chat_id = str(msg.chat.id)

    try:
        from app.db.session import SessionLocal
        from app.models.recruitment import Candidate, TelegramMessage
        db = SessionLocal()
        try:
            candidate = db.query(Candidate).filter(
                Candidate.telegram_chat_id == chat_id
            ).first()
            if not candidate:
                log.debug("business_message from unknown chat_id=%s, skipping", chat_id)
                return

            tg_msg = TelegramMessage(
                candidate_id=candidate.id,
                direction="in",
                text=msg.text,
                tg_message_id=str(msg.message_id),
            )
            db.add(tg_msg)
            db.commit()
            log.info("Saved incoming Telegram message from candidate_id=%s", candidate.id)
        finally:
            db.close()
    except Exception as exc:
        log.warning("handle_business_message error: %s", exc)
