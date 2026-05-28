"""Handle Telegram Secretary Mode (Chat Automation) business_connection updates."""
import asyncio
import logging
from datetime import datetime

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
                    db.commit()

                    if getattr(candidate, 'stage', '') == 'ждем_привязки':
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
                        try:
                            from app.services.ai_conversation import handle_candidate_message
                            asyncio.ensure_future(handle_candidate_message(candidate.id, msg_text))
                        except Exception as e:
                            log.warning("AI conversation trigger error: %s", e)
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

                        # Check if interview was confirmed in this exchange
                        if getattr(candidate, 'stage', '') == 'общение':
                            asyncio.ensure_future(
                                _check_interview_confirmation(candidate.id)
                            )

        finally:
            db.close()
    except Exception as exc:
        log.warning("handle_business_message error: %s", exc)


async def _check_interview_confirmation(candidate_id: int):
    """Use Claude to detect if an interview date/time was confirmed in the conversation."""
    try:
        from app.db.session import SessionLocal
        from app.models.recruitment import Candidate, TelegramMessage
        from app.services.config_service import ConfigService
        from app.services.notify import send_notification

        db = SessionLocal()
        try:
            c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
            if not c or getattr(c, 'stage', '') != 'общение':
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

            client = Anthropic(api_key=api_key, http_client=http_client)
            prompt = (
                "Проанализируй переписку менеджера с кандидатом. "
                "Определи: была ли ПОДТВЕРЖДЕНА конкретная дата и время собеседования обеими сторонами?\n\n"
                f"Переписка:\n{transcript}\n\n"
                'Ответь ТОЛЬКО в формате JSON (без markdown):\n'
                '{"confirmed": true/false, "date": "YYYY-MM-DD или null", "time": "HH:MM или null", "notes": "краткое описание"}\n\n'
                "Confirmed = true ТОЛЬКО если обе стороны явно согласились на конкретные дату и время."
            )

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()

            import json, re
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if not m:
                return
            data = json.loads(m.group())

            if not data.get("confirmed"):
                return

            interview_date = data.get("date")
            interview_time = data.get("time")
            notes_text = data.get("notes", "")

            log.info("Interview confirmed for candidate %s: %s %s", candidate_id, interview_date, interview_time)

            c.stage = 'собеседование'
            c.updated_at = datetime.utcnow()
            db.commit()

            task_info = ""
            try:
                from app.services.task_service import TaskService
                from app.schemas.task import TaskCreate
                from datetime import date as date_cls, time as time_cls

                due_date = None
                due_time_val = None
                if interview_date:
                    try:
                        due_date = date_cls.fromisoformat(interview_date)
                    except Exception:
                        pass
                if interview_time:
                    try:
                        h, mn = interview_time.split(":")
                        due_time_val = time_cls(int(h), int(mn))
                    except Exception:
                        pass

                task_data = TaskCreate(
                    title=f"Собеседование: {c.name}",
                    description=f"Кандидат на вакансию. {notes_text}".strip(),
                    due_date=due_date,
                    due_time=due_time_val,
                )
                svc = TaskService()
                await svc.create_task(task_data, created_by="AI")
                task_info = f"{interview_date or ''} {interview_time or ''}".strip()
                log.info("Created interview task for candidate %s", candidate_id)
            except Exception as e:
                log.warning("Failed to create interview task: %s", e)

            await send_notification(
                f"📅 <b>Собеседование подтверждено!</b>\n"
                f"Кандидат <b>{c.name}</b> переведён на этап «Собеседование».\n"
                + (f"Дата и время: <b>{task_info}</b>\n" if task_info else "")
                + "Задача создана автоматически."
            )

        finally:
            db.close()
    except Exception as e:
        log.warning("_check_interview_confirmation error: %s", e)
