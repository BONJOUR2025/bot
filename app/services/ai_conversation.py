"""Structured AI interview for onboarded candidates."""
import json
import logging
import re
from datetime import date, datetime

log = logging.getLogger(__name__)

# Cap on how many of the most recent dialogue messages are replayed to the LLM
# on each turn. The current interview phase is persisted separately, so older
# turns add little context while inflating input-token cost on every message.
MAX_HISTORY_MESSAGES = 20

DEFAULT_AWAY_MESSAGE = (
    "Здравствуйте! Мы получили ваше сообщение. Наш ассистент отвечает в рабочее время "
    "({hours}) — обязательно продолжим общение, как только начнётся рабочий день. Спасибо за терпение!"
)

# In-memory dedup: candidate_id -> date when the "we'll reply during working hours"
# message was last sent. Keeps a candidate writing repeatedly off-hours from being
# bombarded with the same auto-reply — at most one per calendar day.
_away_notified: dict[int, date] = {}


async def _send_away_reply(c, db, cfg) -> None:
    from app.models.recruitment import TelegramMessage
    from app.services.notify import send_secretary_message
    from app.services.work_hours import describe_hours

    today = date.today()
    if _away_notified.get(c.id) == today:
        return
    _away_notified[c.id] = today

    from app.models.recruitment import Vacancy
    from app.services.strategy_resolver import get_strategy, get_away_message
    vacancy = db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first() if c.vacancy_id else None
    strategy = get_strategy(db, vacancy)
    msg_text = get_away_message(strategy, cfg) or DEFAULT_AWAY_MESSAGE
    if "{hours}" in msg_text:
        msg_text = msg_text.format(hours=describe_hours(cfg))

    err = await send_secretary_message(c.telegram_chat_id, msg_text)
    if err:
        log.warning("AI: failed to send away-reply to candidate %s: %s", c.id, err)
        return
    db.add(TelegramMessage(candidate_id=c.id, direction="out", sent_by_ai=1, text=msg_text))
    db.commit()

SYSTEM_PROMPT = """Ты HR-ассистент компании. Ведёшь структурированное первичное интервью с кандидатом.

ТЕКУЩАЯ ФАЗА: {phase}

База знаний о вакансии:
{knowledge_base}

Место собеседований: {interview_location}

━━━ ИНСТРУКЦИИ ПО ФАЗАМ ━━━

{phases_block}

━━━ ПРАВИЛА ━━━
- Отвечай ТОЛЬКО в JSON: {{"msg": "текст для кандидата", "next_phase": "фаза или null", "unanswered_question": "вопрос кандидата или null"}}
- next_phase = null если текущая фаза продолжается
- unanswered_question ставь ТОЛЬКО если в базе знаний выше нет вообще никакой релевантной информации по теме вопроса.
  Если по теме есть хоть какая-то информация (в том числе в материалах документов, не только в Q&A-записях) —
  обязательно ответь по существу, кратко своими словами пересказав суть из базы знаний, даже если вопрос
  сформулирован широко (например «расскажите о компании» — перескажи в 2–3 предложениях то, что есть в материалах
  про компанию). unanswered_question = null в этом случае. Не уклоняйся от ответа, если информация есть хотя бы частично.
- Максимум 3 коротких предложения в msg
- Нейтрально-деловой тон, без клише и корпоративного новояза
- Только русский язык, обращение на «вы»
- Не задавай два вопроса подряд — один за раз"""


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

        from app.services.work_hours import is_working_now
        if not is_working_now(cfg):
            await _send_away_reply(c, db, cfg)
            return

        from app.services.strategy_resolver import (
            get_strategy, build_ai_context_block, get_interview_location, get_ai_model,
        )

        vacancy = db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first() if c.vacancy_id else None
        strategy = get_strategy(db, vacancy)
        kb_block = build_ai_context_block(db, vacancy)
        interview_location = get_interview_location(vacancy, cfg)
        ai_model = get_ai_model(strategy)

        if not kb_block:
            await send_notification(
                f"🤖 <b>AI: нет базы знаний</b>\nКандидат <b>{c.name}</b> написал, "
                f"но база знаний пуста. Подключитесь к диалогу вручную.\n\nСообщение: {message_text[:200]}"
            )
            return

        custom_questions = []
        if vacancy and vacancy.custom_questions_json:
            try:
                custom_questions = json.loads(vacancy.custom_questions_json) or []
            except Exception:
                custom_questions = []

        from app.services.interview_stages import get_stages, render_stages_block

        # The stage graph is frozen onto the candidate the first time their
        # interview is processed, so a later edit to the strategy's stages
        # (rename/delete) never disrupts a conversation already in progress —
        # only candidates who haven't started yet pick up the new graph.
        stages = None
        if c.stages_snapshot_json:
            try:
                parsed = json.loads(c.stages_snapshot_json)
                if isinstance(parsed, list) and parsed:
                    stages = parsed
            except Exception:
                stages = None
        if stages is None:
            stages = get_stages(strategy)
            c.stages_snapshot_json = json.dumps(stages, ensure_ascii=False)
            db.commit()
        stage_ids = [s["id"] for s in stages]

        phase = getattr(c, "interview_phase", None) or stage_ids[0]
        if phase == "done":
            # Interview already closed and profile already sent — but the
            # candidate kept writing (e.g. a natural follow-up right after the
            # goodbye message). Answer from the knowledge base instead of
            # going silent, but never reopen the phase machine or the profile.
            await _handle_post_interview_message(c, db, cfg, message_text, kb_block)
            return
        if phase not in stage_ids:
            phase = stage_ids[0]

        # If candidate already has conversation history but phase is still the
        # first stage, they pre-date the structured interview — skip ahead
        if phase == stage_ids[0]:
            existing_count = db.query(TelegramMessage).filter(
                TelegramMessage.candidate_id == candidate_id,
                TelegramMessage.direction == "in",
            ).count()
            if existing_count > 1 and len(stage_ids) > 1:  # more than the current message
                phase = stage_ids[1]
                c.interview_phase = phase
                db.commit()

        # Only the tail of the dialogue is sent to the LLM. The interview phase
        # is tracked separately on the candidate, so older turns carry little
        # signal — yet re-sending the full transcript on every incoming message
        # made input-token cost grow quadratically with conversation length
        # (the #1 source of runaway token spend). Cap to the most recent turns.
        history = (
            db.query(TelegramMessage)
            .filter(TelegramMessage.candidate_id == candidate_id)
            .order_by(TelegramMessage.created_at.desc())
            .limit(MAX_HISTORY_MESSAGES)
            .all()
        )
        history.reverse()  # back to chronological order

        messages = []
        for m in history:
            role = "user" if m.direction == "in" else "assistant"
            messages.append({"role": role, "content": m.text})

        # The Anthropic API requires the first message to be from the user, so
        # drop any leading assistant turns left at the head after the cap.
        while messages and messages[0]["role"] != "user":
            messages.pop(0)

        if not messages or messages[-1]["content"] != message_text:
            messages.append({"role": "user", "content": message_text})

        system = SYSTEM_PROMPT.format(
            phase=phase,
            knowledge_base=kb_block,
            interview_location=interview_location or "уточняется",
            phases_block=render_stages_block(stages, custom_questions),
        )

        try:
            raw = chat(cfg, messages, system=system, model=ai_model, max_tokens=300)
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
        unanswered_question = None
        m_json = re.search(r'\{.*\}', raw, re.DOTALL)
        if m_json:
            try:
                data = json.loads(m_json.group())
                reply_text = (data.get("msg") or "").strip()
                next_phase = data.get("next_phase") or None
                unanswered_question = (data.get("unanswered_question") or "").strip() or None
            except Exception as e:
                log.warning(
                    "AI interview: failed to parse JSON response for candidate %s: %s | raw=%r",
                    candidate_id, e, raw[:300],
                )
        else:
            log.warning(
                "AI interview: response had no JSON for candidate %s | raw=%r",
                candidate_id, raw[:300],
            )
        if not reply_text:
            reply_text = raw.replace("**", "").replace("__", "").strip()

        # Update phase — only along a transition actually declared for the
        # current stage, so the builder's drawn arrows are an enforced state
        # machine rather than just descriptive prompt text the AI could ignore.
        cascaded_stage = None
        if next_phase and next_phase != phase:
            current_stage = next((s for s in stages if s["id"] == phase), None)
            allowed = {t.get("next") for t in (current_stage.get("transitions") or [])} if current_stage else set()
            if next_phase in allowed:
                c.interview_phase = next_phase
                # A stage whose ONLY transition is unconditional (e.g. the default
                # "closing" stage, condition="") has nothing left for the candidate
                # to do — the message just sent already used that stage's
                # instructions (the AI sees every stage's text up front, not just
                # the current one). Waiting for another incoming message to reach
                # "done" would hang forever since the candidate has no reason to
                # write again, so cascade straight through.
                #
                # Whichever stage we land in right before cascading is captured —
                # the AI's single reply for this turn was generated while "seeing"
                # every stage's instructions at once, so it may have answered an
                # unrelated question and never actually delivered that stage's own
                # content (e.g. the goodbye / "profile sent to recruiter" message).
                # We re-generate and deliver that stage's content separately below
                # to guarantee the candidate actually receives it.
                while True:
                    s = next((st for st in stages if st["id"] == c.interview_phase), None)
                    trs = (s.get("transitions") or []) if s else []
                    if len(trs) != 1 or (trs[0].get("condition") or "").strip():
                        break
                    cascaded_stage = s
                    nxt = trs[0].get("next") or "done"
                    if nxt == c.interview_phase:
                        break
                    c.interview_phase = nxt
                    next_phase = nxt
                db.commit()
                log.info("Interview phase: candidate_id=%s %s → %s", candidate_id, phase, next_phase)
            else:
                log.warning(
                    "AI tried undeclared phase transition for candidate %s: %s → %s (ignored, staying on %s)",
                    candidate_id, phase, next_phase, phase,
                )
                next_phase = None

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

        # The AI promises the candidate "рекрутер ответит отдельно прямо в этом
        # чате" when it can't answer from the knowledge base — that promise is
        # only true if the admin actually finds out. Without this, the question
        # silently vanishes and the candidate just gets generic follow-ups later.
        # Track it on the candidate too — follow_up_service checks this to avoid
        # sending a generic "still interested?" nudge while a real question is
        # sitting unanswered. Cleared once the admin replies manually in-chat.
        c.pending_question = unanswered_question
        c.pending_question_asked_at = datetime.utcnow() if unanswered_question else None
        db.commit()

        if unanswered_question:
            await send_notification(
                f"❓ <b>Кандидат задал вопрос без ответа в базе знаний</b>\n"
                f"Кандидат: <b>{c.name}</b>\n"
                f"Вопрос: «{unanswered_question}»\n\n"
                f"Ассистент сказал, что вы ответите прямо в этом чате — зайдите в карточку кандидата, "
                f"вкладка Telegram, и ответьте."
            )

        # If the cascade skipped through a stage (e.g. "closing") within this
        # same turn, the main reply above may never have actually delivered
        # that stage's content (it was generated answering whatever the
        # candidate's message was about). Send it as a guaranteed second
        # message so the candidate is actually told the interview is over.
        if cascaded_stage and next_phase == "done":
            await _send_cascaded_stage_message(c, db, cfg, cascaded_stage, kb_block, ai_model)

        # Generate profile when interview ends
        if next_phase == "done":
            import asyncio
            task = asyncio.ensure_future(_generate_candidate_profile(candidate_id))
            task.add_done_callback(lambda t, cid=candidate_id: _log_profile_task_exception(t, cid))

    finally:
        db.close()


async def _send_cascaded_stage_message(c, db, cfg, stage: dict, kb_block: str, ai_model) -> None:
    """Generate and deliver the content of a stage the cascade skipped through
    within the same turn (see comment at the cascade loop), so its content
    (e.g. a goodbye / "profile sent to recruiter" message) actually reaches
    the candidate instead of silently vanishing."""
    from app.models.recruitment import TelegramMessage
    from app.services.notify import send_secretary_message
    from app.services.llm_client import chat

    instructions = (stage.get("instructions") or "").strip()
    if not instructions:
        return

    system = (
        "Ты HR-ассистент компании. Интервью с кандидатом только что завершилось.\n\n"
        f"База знаний о вакансии:\n{kb_block}\n\n"
        f"Задача для этого сообщения: {instructions}\n\n"
        "Напиши ТОЛЬКО текст сообщения кандидату, без JSON и пояснений. "
        "Максимум 3 коротких предложения, на «вы», по-русски, нейтрально-деловой тон."
    )
    try:
        raw = chat(cfg, [{"role": "user", "content": "Сформулируй сообщение"}], system=system, model=ai_model, max_tokens=200)
    except Exception as e:
        log.warning("Cascaded stage message AI error for candidate %s: %s", c.id, e)
        return
    if not raw:
        return
    text = raw.replace("**", "").replace("__", "").strip()

    err = await send_secretary_message(c.telegram_chat_id, text)
    if err:
        log.warning("AI: failed to send cascaded stage message to candidate %s: %s", c.id, err)
        return
    db.add(TelegramMessage(candidate_id=c.id, direction="out", sent_by_ai=1, text=text))
    db.commit()


async def _handle_post_interview_message(c, db, cfg, message_text: str, kb_block: str) -> None:
    """Interview already closed (phase == 'done') but the candidate kept writing —
    e.g. a natural follow-up question right after the goodbye message. Answer
    from the knowledge base same as during the interview, but never reopen the
    phase machine or regenerate the profile."""
    from app.models.recruitment import TelegramMessage
    from app.services.notify import send_secretary_message, send_notification
    from app.services.llm_client import chat

    system = (
        "Ты HR-ассистент компании. Интервью с кандидатом уже завершено, его профиль передан рекрутеру.\n\n"
        f"База знаний о вакансии:\n{kb_block}\n\n"
        "Кандидат написал ещё одно сообщение после завершения интервью. Ответь ТОЛЬКО в JSON: "
        '{"msg": "текст для кандидата", "unanswered_question": "вопрос кандидата или null"}\n'
        "unanswered_question ставь ТОЛЬКО если в базе знаний вообще нет relevant информации по теме — "
        "иначе отвечай по существу, кратко. Максимум 3 коротких предложения, на «вы», по-русски."
    )
    try:
        raw = chat(cfg, [{"role": "user", "content": message_text}], system=system, max_tokens=300)
    except Exception as e:
        log.warning("Post-interview AI error for candidate %s: %s", c.id, e)
        return
    if not raw:
        return

    reply_text = None
    unanswered_question = None
    m_json = re.search(r'\{.*\}', raw, re.DOTALL)
    if m_json:
        try:
            data = json.loads(m_json.group())
            reply_text = (data.get("msg") or "").strip()
            unanswered_question = (data.get("unanswered_question") or "").strip() or None
        except Exception:
            pass
    if not reply_text:
        reply_text = raw.replace("**", "").replace("__", "").strip()

    err = await send_secretary_message(c.telegram_chat_id, reply_text)
    if not err:
        db.add(TelegramMessage(candidate_id=c.id, direction="out", sent_by_ai=1, text=reply_text))
        db.commit()

    c.pending_question = unanswered_question
    c.pending_question_asked_at = datetime.utcnow() if unanswered_question else None
    db.commit()

    if unanswered_question:
        await send_notification(
            f"❓ <b>Кандидат задал вопрос без ответа в базе знаний (после интервью)</b>\n"
            f"Кандидат: <b>{c.name}</b>\n"
            f"Вопрос: «{unanswered_question}»\n\n"
            f"Ассистент сказал, что вы ответите прямо в этом чате — зайдите в карточку кандидата, "
            f"вкладка Telegram, и ответьте."
        )


def _log_profile_task_exception(task, candidate_id: int) -> None:
    """asyncio.ensure_future swallows exceptions unless someone checks the task —
    without this, a crash in _generate_candidate_profile means the admin never
    gets the candidate profile and nothing in the logs says why."""
    exc = task.exception() if not task.cancelled() else None
    if exc:
        log.error("_generate_candidate_profile failed for candidate %s: %s", candidate_id, exc, exc_info=exc)


async def _generate_candidate_profile(candidate_id: int) -> None:
    """Analyze full conversation and send structured candidate profile to admin.
    If profile generation fails at any step, still alert the admin that the
    interview finished — otherwise a candidate reaching "done" while this
    pipeline breaks looks, from the admin's side, like nothing happened at all."""
    from app.services.notify import send_notification

    candidate_name = None
    success = False
    try:
        success, candidate_name = await _generate_candidate_profile_inner(candidate_id)
    except Exception as e:
        log.error("Candidate profile generation crashed for candidate_id=%s: %s", candidate_id, e, exc_info=e)

    if not success:
        await send_notification(
            f"⚠️ <b>Интервью завершено, но профиль не сформирован</b>\n"
            f"Кандидат ID {candidate_id}{f' ({candidate_name})' if candidate_name else ''} прошёл интервью, "
            f"но при формировании профиля произошла ошибка. Посмотрите диалог вручную."
        )


async def _generate_candidate_profile_inner(candidate_id: int) -> tuple[bool, str | None]:
    """Returns (success, candidate_name). candidate_name is set as soon as known,
    for use in fallback error messages even when generation fails partway through."""
    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate, TelegramMessage, Vacancy
    from app.services.config_service import ConfigService
    from app.services.notify import send_notification
    from app.services.llm_client import chat

    db = SessionLocal()
    candidate_name = None
    try:
        c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not c:
            return True, None  # candidate gone — nothing to alert about
        candidate_name = c.name  # read before session closes

        custom_questions = []
        vacancy = db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first() if c.vacancy_id else None
        if vacancy and vacancy.custom_questions_json:
            try:
                custom_questions = json.loads(vacancy.custom_questions_json) or []
            except Exception:
                custom_questions = []

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
    custom_questions_block = ""
    if custom_questions:
        q_lines = "\n".join(f'- "{q}"' for q in custom_questions)
        custom_questions_block = (
            f"\n\nРекрутер просил задать кандидату эти вопросы — найди в транскрипте ответ на каждый "
            f"(или null, если кандидат не ответил) и верни их в поле custom_answers:\n{q_lines}"
        )

    prompt = (
        f"Проанализируй интервью с кандидатом на вакансию и составь профиль.\n\n"
        f"Кандидат: {candidate_name}\n\n"
        f"Транскрипт интервью:\n{transcript}"
        f"{custom_questions_block}\n\n"
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
        '"recommendation_reason": "краткое обоснование"'
        + (', "custom_answers": [{"question": "...", "answer": "... или null"}]' if custom_questions else "")
        + '}'
    )

    raw = chat(cfg, [{"role": "user", "content": prompt}], max_tokens=1500)
    if not raw:
        log.error("Candidate profile generation: empty AI response for candidate_id=%s", candidate_id)
        return False, candidate_name

    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        log.error(
            "Candidate profile generation: no JSON in AI response for candidate_id=%s | raw=%r",
            candidate_id, raw[:300],
        )
        return False, candidate_name

    try:
        p = json.loads(m.group())
    except Exception as e:
        log.error(
            "Candidate profile generation: failed to parse JSON for candidate_id=%s: %s | raw=%r",
            candidate_id, e, raw[:300],
        )
        return False, candidate_name

    db = SessionLocal()
    try:
        c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if c:
            c.profile_json = json.dumps(p, ensure_ascii=False)
            c.profile_generated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()

    rec_emoji = {"invite": "✅", "reserve": "🔶", "reject": "❌"}.get(p.get("recommendation", ""), "❓")
    strengths = "\n".join(f"  + {s}" for s in (p.get("strengths") or []))
    flags = "\n".join(f"  ⚠ {f}" for f in (p.get("red_flags") or []))
    tags = " ".join(f"#{t.replace(' ', '_')}" for t in (p.get("tags") or []))
    custom_answers = "\n".join(
        f"  • {a.get('question', '')}: {a.get('answer') or '—'}" for a in (p.get("custom_answers") or [])
    )

    text = (
        f"👤 <b>Профиль кандидата: {candidate_name}</b>\n\n"
        f"<b>Скор:</b> {p.get('score', '?')}/100 — {p.get('score_reason', '')}\n\n"
        f"<b>Резюме:</b>\n{p.get('summary', '')}\n\n"
    )
    if strengths:
        text += f"<b>Сильные стороны:</b>\n{strengths}\n\n"
    if flags:
        text += f"<b>Красные флаги:</b>\n{flags}\n\n"
    if custom_answers:
        text += f"<b>Ответы на вопросы рекрутера:</b>\n{custom_answers}\n\n"
    if p.get("salary_expectation"):
        text += f"<b>Ожидания по ЗП:</b> {p['salary_expectation']}\n"
    if p.get("availability"):
        text += f"<b>Доступность:</b> {p['availability']}\n"
    if tags:
        text += f"\n{tags}\n"
    text += f"\n{rec_emoji} <b>Рекомендация:</b> {p.get('recommendation_reason', '')}"

    sent = await send_notification(text)
    if sent:
        log.info("Candidate profile sent for candidate_id=%s score=%s", candidate_id, p.get("score"))
    else:
        log.error(
            "Candidate profile generation: send_notification failed for candidate_id=%s "
            "(check notification_chat_id config) — profile lost: %s",
            candidate_id, text[:200],
        )
    return sent, candidate_name

