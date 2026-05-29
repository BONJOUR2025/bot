"""Handle Telegram Secretary Mode (Chat Automation) business_connection updates."""
import asyncio
import logging
from datetime import datetime

log = logging.getLogger(__name__)

# In-memory dedup: candidate_ids currently being processed for interview confirmation
_confirmation_in_progress: set = set()


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
    """Handle incoming business messages — from candidate or from admin."""
    msg = update.business_message
    if not msg:
        return

    chat_id = str(msg.chat.id)
    text = (msg.text or "").strip()
    sender_name = getattr(msg.chat, 'full_name', '') or getattr(msg.chat, 'first_name', '') or ''

    # Determine if this message was sent by the admin (business owner) or the candidate
    from app.services.config_service import ConfigService
    cfg = ConfigService().load()
    # tg_business_user_id is saved on connect event; fall back to ADMIN_ID from env
    business_user_id = str(cfg.get("tg_business_user_id") or "")
    if not business_user_id:
        try:
            from app.config import ADMIN_ID
            if ADMIN_ID:
                business_user_id = str(ADMIN_ID)
        except Exception:
            pass
    sender_id = str(getattr(msg.from_user, 'id', '') if msg.from_user else '')
    is_admin_message = bool(business_user_id and sender_id == business_user_id)
    log.debug("business_msg: sender_id=%s business_user_id=%s is_admin=%s chat_id=%s",
              sender_id, business_user_id, is_admin_message, chat_id)

    # Auto-save business_connection_id from incoming messages if not yet in config
    try:
        conn_id = getattr(msg, 'business_connection_id', None)
        if conn_id and not cfg.get("tg_business_connection_id"):
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
            candidate = db.query(Candidate).filter(
                Candidate.telegram_chat_id == chat_id
            ).first()

            if not is_admin_message:
                # ── Сообщение от кандидата ────────────────────────────────

                # Матчинг по коду CAND-{id}-{token}
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

                # Матчинг по контакту
                if not candidate and msg.contact and msg.contact.phone_number:
                    raw_phone = msg.contact.phone_number
                    digits = re.sub(r'\D', '', raw_phone)[-10:]
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
                    msg_text = text or ('[контакт]' if msg.contact else '[медиа]')
                    tg_msg = TelegramMessage(
                        candidate_id=candidate.id,
                        direction="in",
                        text=msg_text,
                        tg_message_id=str(msg.message_id),
                    )
                    db.add(tg_msg)
                    # Кандидат написал — сбрасываем счётчик follow-up
                    candidate.follow_up_count = 0
                    candidate.follow_up_last_sent_at = None
                    db.commit()

                    # Skip AI entirely if candidate is on pause
                    if getattr(candidate, 'is_paused', False):
                        log.info("AI skipped: candidate_id=%s is paused", candidate.id)
                    elif getattr(candidate, 'stage', '') == 'ждем_привязки':
                        try:
                            candidate.stage = 'общение'
                            candidate.updated_at = datetime.utcnow()
                            db.commit()
                            from app.services.notify import send_notification
                            await send_notification(
                                f"✅ <b>Telegram привязан!</b>\n"
                                f"Кандидат <b>{candidate.name}</b> написал в Telegram и переведён на этап «Общение»."
                            )
                            from app.services.ai_conversation import handle_candidate_message
                            asyncio.ensure_future(handle_candidate_message(candidate.id, msg_text))
                        except Exception as e:
                            log.warning("Stage transition error: %s", e)
                    elif getattr(candidate, 'stage', '') == 'общение':
                        # Check if admin was actively writing manually — if so, AI stays silent
                        last_out = db.query(TelegramMessage).filter(
                            TelegramMessage.candidate_id == candidate.id,
                            TelegramMessage.direction == "out",
                        ).order_by(TelegramMessage.created_at.desc()).first()
                        admin_is_active = last_out is not None and not getattr(last_out, 'sent_by_ai', 0)

                        if admin_is_active:
                            log.info("AI suppressed: last outgoing message was from admin, not AI (candidate_id=%s)", candidate.id)
                        else:
                            try:
                                from app.services.ai_conversation import handle_candidate_message
                                asyncio.ensure_future(handle_candidate_message(candidate.id, msg_text))
                            except Exception as e:
                                log.warning("AI conversation trigger error: %s", e)

                        # Always check if candidate's reply confirms an interview
                        asyncio.ensure_future(_check_interview_confirmation(candidate.id))
                else:
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

            else:
                # ── Сообщение от администратора ───────────────────────────
                # Сохраняем как исходящее, AI не трогаем
                if candidate and text:
                    # Dedup: skip if this message_id already saved
                    already = db.query(TelegramMessage).filter(
                        TelegramMessage.candidate_id == candidate.id,
                        TelegramMessage.tg_message_id == str(msg.message_id),
                    ).first()
                    if already:
                        log.debug("Skipping duplicate admin message msg_id=%s", msg.message_id)
                    else:
                        tg_msg = TelegramMessage(
                            candidate_id=candidate.id,
                            direction="out",
                            text=text,
                            tg_message_id=str(msg.message_id),
                        )
                        db.add(tg_msg)
                        db.commit()
                        log.info("Saved admin→candidate TG message for candidate_id=%s", candidate.id)

                        if getattr(candidate, 'stage', '') == 'общение':
                            # Check if this admin reply follows an AI escalation → self-learning
                            asyncio.ensure_future(
                                _maybe_learn_from_escalation(candidate.id, text)
                            )
                            # Check if interview was confirmed in this exchange
                            asyncio.ensure_future(
                                _check_interview_confirmation(candidate.id)
                            )

        finally:
            db.close()
    except Exception as exc:
        log.warning("handle_business_message error: %s", exc)


async def _maybe_learn_from_escalation(candidate_id: int, admin_answer: str):
    """
    Detect pattern: candidate question → AI escalation → admin answer.
    If found and this is the FIRST admin reply after the escalation, trigger learning.
    """
    try:
        from app.db.session import SessionLocal
        from app.models.recruitment import TelegramMessage

        db = SessionLocal()
        try:
            # Load last 10 messages ordered by time
            history = db.query(TelegramMessage).filter(
                TelegramMessage.candidate_id == candidate_id
            ).order_by(TelegramMessage.created_at.desc()).limit(10).all()
            history = list(reversed(history))

            if len(history) < 3:
                return

            # Find the most recent escalation message
            esc_idx = None
            for i, m in enumerate(history):
                if getattr(m, 'is_ai_escalation', 0):
                    esc_idx = i

            if esc_idx is None:
                return

            # Count admin ("out") messages AFTER the escalation (excluding escalation itself)
            admin_after = [
                m for m in history[esc_idx + 1:]
                if m.direction == "out"
            ]
            # Only learn from the FIRST admin reply after escalation
            if len(admin_after) != 1:
                return

            # Find the candidate's question: last "in" message before the escalation
            question = None
            for m in reversed(history[:esc_idx]):
                if m.direction == "in":
                    question = m.text
                    break

            if not question:
                return

            log.info("Auto-learning triggered for candidate_id=%s question=%s",
                     candidate_id, question[:80])
        finally:
            db.close()

        from app.services.learning_service import learn_from_escalation
        await learn_from_escalation(candidate_id, question, admin_answer)

    except Exception as e:
        log.warning("_maybe_learn_from_escalation error: %s", e)


async def _check_interview_confirmation(candidate_id: int):
    """Use Claude to detect if an interview date/time was confirmed in the conversation."""
    # In-process dedup: prevent parallel runs for same candidate
    if candidate_id in _confirmation_in_progress:
        log.debug("_check_interview_confirmation: already running for candidate_id=%s, skipping", candidate_id)
        return
    _confirmation_in_progress.add(candidate_id)
    try:
        from app.db.session import SessionLocal
        from app.models.recruitment import Candidate, TelegramMessage, Vacancy
        from app.services.config_service import ConfigService
        from app.services.notify import send_notification, send_secretary_message
        import json, re
        from datetime import date as date_cls, time as time_cls, datetime as dt_cls, timedelta

        db = SessionLocal()
        try:
            c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
            if not c or getattr(c, 'stage', '') != 'общение':
                return
            if getattr(c, 'is_paused', False):
                return
            # 10-minute dedup: skip if admin was already notified recently
            notified_at = getattr(c, 'interview_notified_at', None)
            if notified_at and (datetime.utcnow() - notified_at) < timedelta(minutes=10):
                log.debug("_check_interview_confirmation: notified recently for candidate_id=%s, skipping", candidate_id)
                return

            history = db.query(TelegramMessage).filter(
                TelegramMessage.candidate_id == candidate_id
            ).order_by(TelegramMessage.created_at.desc()).limit(20).all()
            history = list(reversed(history))

            if len(history) < 2:
                return

            lines = []
            for m in history:
                who = "Менеджер" if m.direction == "out" else "Кандидат"
                lines.append(f"{who}: {m.text}")
            transcript = "\n".join(lines)

            cfg = ConfigService().load()
            api_key = (cfg.get("anthropic_api_key") or "").strip() or None
            if not api_key:
                return

            from anthropic import Anthropic
            proxy_url = None
            try:
                from app.settings import settings as _s
                proxy_url = getattr(_s, "telegram_proxy", None)
            except Exception:
                pass
            http_client = None
            if proxy_url:
                import httpx
                http_client = httpx.Client(proxy=proxy_url)

            today_str = date_cls.today().isoformat()  # передаём чтобы Claude резолвил "завтра", "в пятницу" и т.д.

            client = Anthropic(api_key=api_key, http_client=http_client)
            prompt = (
                f"Сегодня {today_str}.\n"
                "Проанализируй переписку менеджера с кандидатом на собеседование.\n"
                "Определи: договорились ли обе стороны о конкретном времени и месте встречи?\n\n"
                f"Переписка:\n{transcript}\n\n"
                "Правила:\n"
                "- confirmed = true ТОЛЬКО если обе стороны явно согласились на конкретные дату, время и место\n"
                "- Преобразуй относительные даты в абсолютные на основе сегодняшней даты\n"
                "- Время может быть неточным (\"часа в 3\" → \"15:00\")\n"
                "- place — извлеки адрес/место из переписки (если упоминался в тексте)\n"
                "- Если время не уточнено, но дата есть — time = null\n"
                "- Если место не упоминалось — place = null\n\n"
                'Ответь ТОЛЬКО в формате JSON (без markdown):\n'
                '{"confirmed": true/false, "date": "YYYY-MM-DD или null", "time": "HH:MM или null", "place": "адрес/место или null", "notes": "краткое описание договорённости"}'
            )

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()

            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if not m:
                return
            data = json.loads(m.group())

            if not data.get("confirmed"):
                return

            interview_date = data.get("date")   # "YYYY-MM-DD" or None
            interview_time = data.get("time")   # "HH:MM" or None
            notes_text = data.get("notes", "")

            log.info("Interview tentatively agreed for candidate %s: %s %s", candidate_id, interview_date, interview_time)

            # Место: сначала из переписки (Claude извлёк), затем фоллбэк на вакансию/конфиг
            place_from_conv = (data.get("place") or "").strip()
            vacancy = db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first() if c.vacancy_id else None
            place_from_cfg = (
                getattr(vacancy, "interview_location", "") or cfg.get("automation_interview_location", "")
            ).strip()
            place = place_from_conv or place_from_cfg

            # Сохраняем pending данные — этап НЕ меняем, задачу НЕ создаём
            c.pending_interview_date = interview_date
            c.pending_interview_time = interview_time
            c.pending_interview_place = place
            db.commit()

            # Кандидату: "уточню с руководителем"
            pending_reply = (cfg.get("ai_interview_pending_reply") or "").strip() or \
                "Отлично! Уточню детали с руководителем и вернусь к вам в ближайшее время."
            err = await send_secretary_message(c.telegram_chat_id, pending_reply)
            if not err:
                out_msg = TelegramMessage(candidate_id=candidate_id, direction="out",
                                          text=pending_reply, sent_by_ai=1)
                db.add(out_msg)
                db.commit()

            # Mark notified before sending so parallel calls see it
            c.interview_notified_at = datetime.utcnow()
            db.commit()

            # Тебе: уведомление с кнопками
            summary_parts = [interview_date, interview_time, place]
            interview_summary = "  ".join(p for p in summary_parts if p)
            place_warning = "\n\n⚠️ <b>Место не указано!</b> Укажите через «✏️ Другое» перед подтверждением." if not place else ""
            from app.services.notify import send_notification_with_keyboard
            await send_notification_with_keyboard(
                f"📅 <b>Кандидат согласовал собеседование!</b>\n"
                f"Кандидат: <b>{c.name}</b>\n"
                f"Время и место: <b>{interview_summary or 'не уточнено'}</b>"
                f"{place_warning}\n\n"
                f"Подтвердить запись или изменить условия?",
                [[
                    {"text": "✅ Подтвердить", "callback_data": f"iview_ok_{candidate_id}"},
                    {"text": "✏️ Другое", "callback_data": f"iview_other_{candidate_id}"},
                ]]
            )

        finally:
            db.close()
    except Exception as e:
        log.warning("_check_interview_confirmation error: %s", e)
    finally:
        _confirmation_in_progress.discard(candidate_id)
