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
        personal_username = getattr(conn.user, 'username', None) or ""
        svc.patch({
            "tg_business_connection_id": conn.id,
            "tg_business_user_id": conn.user_id,
            "tg_business_can_reply": conn.can_reply,
            "tg_personal_username": personal_username,
        })
        log.info("Secretary Mode connected: user_id=%s connection_id=%s can_reply=%s username=%s",
                 conn.user_id, conn.id, conn.can_reply, personal_username)
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
    if not msg:
        return

    chat_id = str(msg.chat.id)
    text = (msg.text or "").strip()
    sender_name = getattr(msg.chat, 'full_name', '') or getattr(msg.chat, 'first_name', '') or ''

    # Auto-save business_connection_id from incoming messages if not yet in config
    try:
        conn_id = getattr(msg, 'business_connection_id', None)
        if conn_id:
            from app.services.config_service import ConfigService
            cfg = ConfigService().load()
            if not cfg.get("tg_business_connection_id"):
                ConfigService().patch({
                    "tg_business_connection_id": conn_id,
                    "tg_business_can_reply": True,
                })
                log.info("Auto-saved business_connection_id=%s from incoming message", conn_id)
    except Exception as e:
        log.warning("Failed to auto-save business_connection_id: %s", e)

    try:
        from app.db.session import SessionLocal
        from app.models.recruitment import Candidate, TelegramMessage, UnlinkedTelegramMessage
        import re

        db = SessionLocal()
        try:
            # 1. Найти по уже известному chat_id
            candidate = db.query(Candidate).filter(
                Candidate.telegram_chat_id == chat_id
            ).first()

            # 2. Матчинг по коду CAND-{id}-{token}
            if not candidate and text:
                m = re.match(r'^CAND-(\d+)-[A-Z0-9]{6}$', text)
                if m:
                    cand_id = int(m.group(1))
                    c = db.query(Candidate).filter(
                        Candidate.id == cand_id,
                        Candidate.telegram_link_code == text,
                    ).first()
                    if c:
                        c.telegram_chat_id = chat_id
                        db.commit()
                        candidate = c
                        log.info("Telegram matched by code: candidate_id=%s chat_id=%s", c.id, chat_id)

            # 3. Матчинг по контакту (кандидат поделился номером телефона)
            if not candidate and msg.contact and msg.contact.phone_number:
                raw_phone = msg.contact.phone_number
                digits = re.sub(r'\D', '', raw_phone)[-10:]  # последние 10 цифр
                all_cands = db.query(Candidate).filter(Candidate.phone.isnot(None)).all()
                for c in all_cands:
                    c_digits = re.sub(r'\D', '', c.phone or '')[-10:]
                    if c_digits and c_digits == digits:
                        c.telegram_chat_id = chat_id
                        db.commit()
                        candidate = c
                        log.info("Telegram matched by phone: candidate_id=%s chat_id=%s", c.id, chat_id)
                        break

            if candidate:
                # Сохранить сообщение
                msg_text = text or ('[контакт]' if msg.contact else '[медиа]')
                if msg_text:
                    tg_msg = TelegramMessage(
                        candidate_id=candidate.id,
                        direction="in",
                        text=msg_text,
                        tg_message_id=str(msg.message_id),
                    )
                    db.add(tg_msg)
                    db.commit()
                    log.info("Saved TG message from candidate_id=%s", candidate.id)
            else:
                # 4. Сохранить как непривязанное сообщение
                msg_text = text or ('[контакт]' if msg.contact else '[медиа]')
                unlinked = UnlinkedTelegramMessage(
                    chat_id=chat_id,
                    sender_name=sender_name,
                    text=msg_text,
                    tg_message_id=str(msg.message_id),
                )
                db.add(unlinked)
                db.commit()
                log.info("Saved unlinked TG message from chat_id=%s name=%s", chat_id, sender_name)
        finally:
            db.close()
    except Exception as exc:
        log.warning("handle_business_message error: %s", exc)
