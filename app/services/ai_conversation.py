"""Structured AI interview for onboarded candidates."""
import json
import logging
import re

log = logging.getLogger(__name__)

# Interview phase order
PHASES = ["greeting", "screening", "experience", "motivation", "candidate_questions", "closing"]

SYSTEM_PROMPT = """Ты HR-ассистент компании. Ведёшь структурированное первичное интервью с кандидатом.

ТЕКУЩАЯ ФАЗА: {phase}

База знаний о вакансии:
{knowledge_base}

Место собеседований: {interview_location}

━━━ ИНСТРУКЦИИ ПО ФАЗАМ ━━━

ФАЗА greeting — Приветствие:
Представься как HR-ассистент компании, упомяни название роли, скажи что задашь несколько вопросов
для первичного знакомства (10–15 минут). Спроси готов ли кандидат.
→ next_phase: "screening" когда кандидат выразил готовность

ФАЗА screening — Deal-breaker скрининг:
Проверь 2–3 критичных параметра из базы знаний (локация, формат работы, зарплатные ожидания).
Задавай по одному вопросу. Если кандидат не подходит — вежливо заверши.
→ next_phase: "experience" когда все deal-breakers проверены и кандидат подходит
→ next_phase: "rejected" если не соответствует

ФАЗА experience — Опыт и стек:
Задавай открытые ситуационные вопросы: «Расскажите о проекте где...», «Что именно было сложно и как справились?»
Уточняй по ответам. Задай 2–3 вопроса суммарно.
→ next_phase: "motivation" после 2–3 вопросов

ФАЗА motivation — Мотивация:
Спроси почему меняет работу, что важно в следующем месте, цели на 1–2 года.
Нейтральная позиция без осуждения.
→ next_phase: "candidate_questions" после ответа

ФАЗА candidate_questions — Вопросы кандидата:
Скажи: «Что вам важно узнать о роли или команде?»
Отвечай честно на всё что есть в базе знаний. Чего нет — «Зафиксирую, рекрутер ответит отдельно».
→ next_phase: "closing" когда вопросы исчерпаны

ФАЗА closing — Финал:
Поблагодари за время. Скажи чёткий следующий шаг: «Передам ваш профиль рекрутеру, ответ получите
до [срок из базы знаний или "в течение 2–3 рабочих дней"]. Если появятся вопросы — пишите сюда.»
→ next_phase: "done"

ФАЗА rejected — Отказ по deal-breaker:
Вежливо и честно объясни что вакансия не совпадает с условиями кандидата. Без осуждения.
→ next_phase: "done"

━━━ ПРАВИЛА ━━━
- Отвечай ТОЛЬКО в JSON: {"msg": "текст для кандидата", "next_phase": "фаза или null"}
- next_phase = null если текущая фаза продолжается
- Максимум 3 коротких предложения в msg
- Нейтрально-деловой тон, без клише и корпоративного новояза
- Только русский язык, обращение на «вы»
- Не задавай два вопроса подряд — один за раз"""


def _build_knowledge_base_block(global_kb: str, vacancy_kb: str) -> str:
    global_kb = global_kb.strip()
    vacancy_kb = vacancy_kb.strip()
    if global_kb and vacancy_kb:
        return (
            "Общая база знаний (компания):\n" + global_kb +
            "\n\nБаза знаний вакансии (приоритет выше):\n" + vacancy_kb +
            "\n\nПри противоречии — используй данные вакансии."
        )
    return "База знаний:\n" + (vacancy_kb or global_kb)


async def handle_candidate_message(candidate_id: int, message_text: str) -> None:
    """Process incoming TG message for a candidate in 'общение' stage."""
    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate, TelegramMessage, Vacancy
    from app.services.config_service import ConfigService
    from app.services.notify import send_secretary_message, send_notification
    from app.services.llm_client import chat

    db = SessionLocal()
    try:
        c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not c or not c.telegram_chat_id:
            return

        cfg = ConfigService().load()
        vacancy = db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first() if c.vacancy_id else None
        global_kb = cfg.get("automation_knowledge_base", "").strip()
        vacancy_kb = getattr(vacancy, "knowledge_base", "").strip() if vacancy else ""
        interview_location = (
            getattr(vacancy, "interview_location", "") or cfg.get("automation_interview_location", "")
        ).strip()

        if not global_kb and not vacancy_kb:
            await send_notification(
                f"🤖 <b>AI: нет базы знаний</b>\nКандидат <b>{c.name}</b> написал, "
                f"но база знаний пуста. Подключитесь к диалогу вручную.\n\nСообщение: {message_text[:200]}"
            )
            return

        phase = getattr(c, "interview_phase", None) or "greeting"
        if phase == "done":
            return

        # If candidate already has conversation history but phase is still "greeting",
        # they pre-date the structured interview — skip to experience phase
        if phase == "greeting":
            existing_count = db.query(TelegramMessage).filter(
                TelegramMessage.candidate_id == candidate_id,
                TelegramMessage.direction == "in",
            ).count()
            if existing_count > 1:  # more than the current message
                phase = "experience"
                c.interview_phase = "experience"
                db.commit()

        history = db.query(TelegramMessage).filter(
            TelegramMessage.candidate_id == candidate_id
        ).order_by(TelegramMessage.created_at).all()

        messages = []
        for m in history:
            role = "user" if m.direction == "in" else "assistant"
            messages.append({"role": role, "content": m.text})

        if not messages or messages[-1]["content"] != message_text:
            messages.append({"role": "user", "content": message_text})

        kb_block = _build_knowledge_base_block(global_kb, vacancy_kb)
        system = SYSTEM_PROMPT.format(
            phase=phase,
            knowledge_base=kb_block,
            interview_location=interview_location or "уточняется",
        )

        try:
            raw = chat(cfg, messages, system=system, max_tokens=300)
            if not raw:
                await send_notification(
                    f"⚠️ <b>AI ошибка</b>\nAPI key не настроен для кандидата <b>{c.name}</b>."
                )
                return
        except Exception as e:
            log.warning("AI interview error for candidate %s: %s", candidate_id, e)
            await send_notification(
                f"⚠️ <b>AI ошибка</b>\nНе удалось получить ответ для кандидата <b>{c.name}</b>.\n"
                f"Подключитесь вручную. Ошибка: {e}"
            )
            return

        # Parse JSON response
        reply_text = None
        next_phase = None
        m_json = re.search(r'\{.*\}', raw, re.DOTALL)
        if m_json:
            try:
                data = json.loads(m_json.group())
                reply_text = (data.get("msg") or "").strip()
                next_phase = data.get("next_phase") or None
            except Exception:
                pass
        if not reply_text:
            reply_text = raw.replace("**", "").replace("__", "").strip()

        # Update phase
        if next_phase and next_phase != phase:
            c.interview_phase = next_phase
            db.commit()
            log.info("Interview phase: candidate_id=%s %s → %s", candidate_id, phase, next_phase)

        # Send reply to candidate
        err = await send_secretary_message(c.telegram_chat_id, reply_text)
        if err:
            log.warning("AI: failed to send reply to candidate %s: %s", candidate_id, err)
        else:
            out_msg = TelegramMessage(
                candidate_id=candidate_id,
                direction="out",
                sent_by_ai=1,
                text=reply_text,
            )
            db.add(out_msg)
            db.commit()

        # Generate profile when interview ends
        if next_phase == "done":
            import asyncio
            asyncio.ensure_future(_generate_candidate_profile(candidate_id))

    finally:
        db.close()


async def _generate_candidate_profile(candidate_id: int) -> None:
    """Analyze full conversation and send structured candidate profile to admin."""
    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate, TelegramMessage
    from app.services.config_service import ConfigService
    from app.services.notify import send_notification
    from app.services.llm_client import chat

    db = SessionLocal()
    try:
        c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not c:
            return
        candidate_name = c.name  # read before session closes

        history = db.query(TelegramMessage).filter(
            TelegramMessage.candidate_id == candidate_id
        ).order_by(TelegramMessage.created_at).all()

        lines = [
            f"{'Кандидат' if m.direction == 'in' else 'Ассистент'}: {m.text}"
            for m in history
        ]
        transcript = "\n".join(lines)
    finally:
        db.close()

    cfg = ConfigService().load()
    prompt = (
        f"Проанализируй интервью с кандидатом на вакансию и составь профиль.\n\n"
        f"Кандидат: {candidate_name}\n\n"
        f"Транскрипт интервью:\n{transcript}\n\n"
        "Верни ТОЛЬКО JSON:\n"
        '{"score": 0-100, '
        '"score_reason": "1-2 предложения почему такой балл", '
        '"tags": ["тег1", "тег2"], '
        '"salary_expectation": "ожидания или null", '
        '"availability": "когда может выйти или null", '
        '"strengths": ["сильная сторона 1", "сильная сторона 2"], '
        '"red_flags": ["флаг 1"], '
        '"summary": "5-7 строк — резюме кандидата для рекрутера", '
        '"recommendation": "invite/reserve/reject", '
        '"recommendation_reason": "краткое обоснование"}'
    )

    raw = chat(cfg, [{"role": "user", "content": prompt}], max_tokens=600)
    if not raw:
        return

    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        return

    try:
        p = json.loads(m.group())
    except Exception:
        return

    rec_emoji = {"invite": "✅", "reserve": "🔶", "reject": "❌"}.get(p.get("recommendation", ""), "❓")
    strengths = "\n".join(f"  + {s}" for s in (p.get("strengths") or []))
    flags = "\n".join(f"  ⚠ {f}" for f in (p.get("red_flags") or []))
    tags = " ".join(f"#{t.replace(' ', '_')}" for t in (p.get("tags") or []))

    text = (
        f"👤 <b>Профиль кандидата: {candidate_name}</b>\n\n"
        f"<b>Скор:</b> {p.get('score', '?')}/100 — {p.get('score_reason', '')}\n\n"
        f"<b>Резюме:</b>\n{p.get('summary', '')}\n\n"
    )
    if strengths:
        text += f"<b>Сильные стороны:</b>\n{strengths}\n\n"
    if flags:
        text += f"<b>Красные флаги:</b>\n{flags}\n\n"
    if p.get("salary_expectation"):
        text += f"<b>Ожидания по ЗП:</b> {p['salary_expectation']}\n"
    if p.get("availability"):
        text += f"<b>Доступность:</b> {p['availability']}\n"
    if tags:
        text += f"\n{tags}\n"
    text += f"\n{rec_emoji} <b>Рекомендация:</b> {p.get('recommendation_reason', '')}"

    await send_notification(text)
    log.info("Candidate profile sent for candidate_id=%s score=%s", candidate_id, p.get("score"))

