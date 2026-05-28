"""Claude AI conversation handler for onboarded candidates."""
import logging
from anthropic import Anthropic

log = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """Ты вежливый HR-ассистент компании. Отвечай на вопросы кандидата о вакансии и условиях работы.

База знаний о компании и вакансии:
{knowledge_base}

Место проведения собеседований: {interview_location}

Правила:
1. Отвечай только на основе предоставленной базы знаний.
2. Если вопрос выходит за рамки базы знаний — ответь ТОЛЬКО словом: ESCALATE
3. Если кандидат говорит что вопросов нет или хочет назначить собеседование — ответь: PROPOSE_INTERVIEW
4. Будь кратким и дружелюбным. Пиши на русском.
"""


async def handle_candidate_message(candidate_id: int, message_text: str) -> None:
    """Process incoming TG message for a candidate in 'общение' stage."""
    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate, TelegramMessage
    from app.services.config_service import ConfigService
    from app.services.notify import send_secretary_message, send_notification

    db = SessionLocal()
    try:
        c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not c or not c.telegram_chat_id:
            return

        cfg = ConfigService().load()
        knowledge_base = cfg.get("automation_knowledge_base", "").strip()
        interview_location = cfg.get("automation_interview_location", "").strip()

        if not knowledge_base:
            # No knowledge base — escalate immediately
            await send_notification(
                f"🤖 <b>AI: нет базы знаний</b>\nКандидат <b>{c.name}</b> написал в Telegram, "
                f"но база знаний пуста. Подключитесь к диалогу вручную.\n\n"
                f"Сообщение: {message_text[:200]}"
            )
            return

        # Build conversation history from DB
        history = db.query(TelegramMessage).filter(
            TelegramMessage.candidate_id == candidate_id
        ).order_by(TelegramMessage.created_at).all()

        messages = []
        for m in history:
            role = "user" if m.direction == "in" else "assistant"
            messages.append({"role": role, "content": m.text})

        # Ensure last message is the current one
        if not messages or messages[-1]["content"] != message_text:
            messages.append({"role": "user", "content": message_text})

        system = SYSTEM_PROMPT_TEMPLATE.format(
            knowledge_base=knowledge_base,
            interview_location=interview_location or "уточняется",
        )

        try:
            client = Anthropic()
            response = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=500,
                system=system,
                messages=messages,
            )
            reply = response.content[0].text.strip()
        except Exception as e:
            log.warning("AI conversation error for candidate %s: %s", candidate_id, e)
            await send_notification(
                f"⚠️ <b>AI ошибка</b>\nНе удалось получить ответ Claude для кандидата <b>{c.name}</b>.\n"
                f"Подключитесь вручную. Ошибка: {e}"
            )
            return

        if reply == "ESCALATE":
            await send_notification(
                f"🙋 <b>AI: нужна помощь</b>\nКандидат <b>{c.name}</b> задал вопрос вне базы знаний.\n"
                f"Вопрос: {message_text[:200]}\n\nПодключитесь к диалогу в Telegram."
            )
            return

        if reply == "PROPOSE_INTERVIEW":
            location_text = f" в {interview_location}" if interview_location else ""
            reply = (
                f"Отлично! Предлагаем пройти собеседование{location_text}. "
                f"Напишите удобные для вас дату и время — мы подтвердим или предложим альтернативу."
            )

        # Send AI reply via Secretary Mode
        err = await send_secretary_message(c.telegram_chat_id, reply)
        if err:
            log.warning("AI: failed to send TG reply to candidate %s: %s", candidate_id, err)
        else:
            # Save outgoing message to DB
            out_msg = TelegramMessage(
                candidate_id=candidate_id,
                direction="out",
                text=reply,
            )
            db.add(out_msg)
            db.commit()
    finally:
        db.close()
