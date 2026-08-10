"""«Быстрый режим»: screen a candidate with a few questions in the job board's
own chat (hh.ru / Avito), then hand the conversation to the admin.

Deliberately much smaller than the Telegram interview in ai_conversation.py:
there is no stage graph, no knowledge-base answering and no scoring. The bot
greets the candidate, confirms they're still looking for work, then asks the
vacancy's quick_questions one at a time, collects the raw answers, and alerts
the admin — who takes over from there.

Flow:
  new response             → greet + "вы ещё в поиске работы?"
  still looking             → question 1
  no longer looking         → polite goodbye, candidate moved to «отказ»
  candidate answers         → next question
  all questions answered    → thank candidate + alert admin with every answer
  counter-question           → stop asking, alert, stay silent (do NOT answer it)
  silent for 24h             → alert

State lives in Candidate.quick_state_json:
  {"status": "asking"|"waiting_admin"|"done",
   "phase": "interest"|"questions",  # "вы ещё в поиске?" vs the real questions;
                                      # absent (legacy rows) means "questions"
   "idx": int,                       # index of the question awaiting an answer
   "answers": [{"q": str, "a": str}],
   "asked_at": iso str,              # when the pending question was sent
   "last_msg_id": str,               # last platform message already processed
   "silence_alerted": bool}
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

SILENCE_AFTER = timedelta(hours=24)

INTEREST_QUESTION = "Подскажите, вы ещё в поиске работы?"
CLOSING_MESSAGE = "Спасибо за ответы! Мы свяжемся с вами в ближайшее время, чтобы договориться о собеседовании."
DECLINE_FAREWELL = "Понял вас, спасибо за ответ! Если что-то изменится — будем рады снова пообщаться. Хорошего дня!"

# Fallback counter-question detector, used only when the LLM is unavailable.
# Deliberately broad: over-alerting merely hands the chat to the admin a bit
# early (which is the desired end state anyway), while missing a question
# would leave the candidate ignored.
_QUESTION_HINT = re.compile(
    r"\?|\b(сколько|какая|какие|какой|когда|где|почему|зачем|можно ли|а что|"
    r"есть ли|как\s|что по)\b",
    re.IGNORECASE,
)

# Fallback "no longer looking" detector for the interest-check reply, used
# only when the LLM is unavailable. Deliberately narrow (unlike
# _QUESTION_HINT) — _looks_still_interested defaults to True on anything it
# doesn't recognise, since misreading a real "да" as "нет" silently drops an
# interested candidate, while the reverse just asks a few extra questions.
_NOT_LOOKING_HINT = re.compile(
    r"\bнет\b|не\s*ищу|уже\s*наш[её]л|уже\s*устро|нашл?а?\s*работу|"
    r"не\s*актуальн|неактуальн|передумал|не\s*нужн|не\s*интересн",
    re.IGNORECASE,
)


def is_quick_mode(vacancy) -> bool:
    return bool(vacancy and getattr(vacancy, "quick_mode_enabled", False) and get_questions(vacancy))


def get_questions(vacancy) -> list[str]:
    raw = getattr(vacancy, "quick_questions_json", None) if vacancy else None
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [q.strip() for q in parsed if isinstance(q, str) and q.strip()]


def load_state(candidate) -> dict:
    raw = getattr(candidate, "quick_state_json", None)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def save_state(db, candidate, state: dict) -> None:
    candidate.quick_state_json = json.dumps(state, ensure_ascii=False)
    db.commit()


# Длиннее, чем показывает карточка, но достаточно коротко, чтобы простыня
# от кандидата не раздувала hr.db, который делят бот и API.
_LAST_MESSAGE_MAX_CHARS = 500


def record_last_message(db, candidate, text: str, direction: str, when: datetime | None = None) -> None:
    """Запомнить последнюю реплику переписки для показа в карточке воронки.

    Best-effort: витрина не должна ронять отправку сообщения кандидату, ради
    которой всё и затевалось, поэтому любая ошибка здесь только логируется.
    """
    text = (text or "").strip()
    if not text:
        return
    try:
        candidate.last_message_text = text[:_LAST_MESSAGE_MAX_CHARS]
        candidate.last_message_at = when or datetime.utcnow()
        candidate.last_message_from = direction
        db.commit()
    except Exception:
        log.warning("quick_screening: failed to record last message for candidate %s",
                    getattr(candidate, "id", "?"), exc_info=True)


async def _send(db, candidate, src, token: str, text: str) -> str | None:
    """Send a message to the candidate on their own platform.
    Returns None on success, or a human-readable error string."""
    from app.services import hh_api, avito_api

    try:
        if candidate.source == "hh":
            if not candidate.external_id:
                return "нет id отклика hh"
            await hh_api.send_message(token, candidate.external_id, text)
            record_last_message(db, candidate, text, "employer")
            return None
        if candidate.source == "avito":
            chat_id = (getattr(candidate, "platform_chat_id", "") or "").strip()
            if not chat_id:
                # Applies of type "by_call" have no chat at all — there is
                # nothing to write to, and that is a data fact, not a failure.
                return "у отклика нет чата на Авито (кандидат оставил только телефон)"
            await avito_api.send_message(token, src.employer_id, chat_id, text)
            record_last_message(db, candidate, text, "employer")
            return None
        return f"неподдерживаемый источник {candidate.source!r}"
    except Exception as e:
        return str(e)


def _candidate_label(candidate, vacancy) -> str:
    src_label = {"hh": "hh.ru", "avito": "Авито"}.get(candidate.source, candidate.source or "?")
    vac = f"\nВакансия: {vacancy.title}" if vacancy else ""
    return f"<b>{candidate.name}</b> ({src_label}){vac}"


async def start_screening(db, candidate, vacancy, src, token: str) -> bool:
    """Kick off the screen for a freshly-arrived response: alert the admin,
    then ask the first question. Returns True if the first question was sent."""
    from app.services.notify import send_notification

    if candidate.is_paused:
        return False  # ИИ-автоматизация поставлена на паузу для этого кандидата
    questions = get_questions(vacancy)
    if not questions:
        return False
    if load_state(candidate):
        return False  # already started

    await send_notification(
        f"⚡ <b>Новый отклик — бот начал опрос</b>\n{_candidate_label(candidate, vacancy)}\n\n"
        f"Уточняю, актуален ли ещё поиск работы, затем задам {len(questions)} вопрос(ов)."
    )

    greeting = f"Здравствуйте!\n\n{INTEREST_QUESTION}"
    err = await _send(db, candidate, src, token, greeting)
    if err:
        log.warning("quick_screening: failed to send greeting to candidate %s: %s", candidate.id, err)
        await send_notification(
            f"⚠️ <b>Не удалось написать кандидату</b>\n{_candidate_label(candidate, vacancy)}\n\n"
            f"Ошибка: {err}\nОтветьте вручную на площадке."
        )
        # Mark as needing the admin rather than retrying forever on every sync.
        save_state(db, candidate, {
            "status": "waiting_admin", "reason": "send_failed", "phase": "interest", "idx": 0, "answers": [],
            "asked_at": datetime.utcnow().isoformat(), "last_msg_id": "",
            "silence_alerted": False,
        })
        return False

    save_state(db, candidate, {
        "status": "asking", "phase": "interest", "idx": 0, "answers": [],
        "asked_at": datetime.utcnow().isoformat(), "last_msg_id": "",
        "silence_alerted": False,
    })
    log.info("quick_screening: started for candidate_id=%s", candidate.id)
    return True


def _looks_like_question(text: str, cfg: dict) -> bool:
    """Is the candidate asking us something instead of answering?

    Uses the LLM when configured (Russian replies often omit a question mark —
    "сколько платите" is a question with no "?"), falling back to a keyword
    gate so this never becomes a hard dependency on the AI provider.
    """
    from app.services.llm_client import chat, get_client

    if not get_client(cfg):
        return bool(_QUESTION_HINT.search(text))

    try:
        raw = chat(
            cfg,
            [{"role": "user", "content": text}],
            system=(
                "Сообщение кандидата в ответ на вопрос рекрутера. Определи, задаёт ли "
                "кандидат встречный вопрос (о зарплате, графике, условиях и т.п.) вместо "
                'ответа или вместе с ним. Ответь ТОЛЬКО JSON: {"question": true/false}'
            ),
            max_tokens=20,
            # Not tied to a staff member — a fixed pseudo-employee bucket so
            # this shows up as its own line in Расход AI по сотрудникам
            # instead of being invisible next to the knowledge-base spend.
            employee_id="quick_screening",
            employee_name="Быстрый режим (кандидаты)",
            feature="quick_screening",
        )
    except Exception as e:
        log.warning("quick_screening: question-detection LLM call failed: %s", e)
        return bool(_QUESTION_HINT.search(text))

    if not raw:
        return bool(_QUESTION_HINT.search(text))
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return bool(_QUESTION_HINT.search(text))
    try:
        return bool(json.loads(m.group()).get("question"))
    except Exception:
        return bool(_QUESTION_HINT.search(text))


def _looks_still_interested(text: str, cfg: dict) -> bool:
    """Is the candidate still looking for work, per their reply to
    INTEREST_QUESTION? Defaults to True on any uncertainty — see
    _NOT_LOOKING_HINT for why a false "нет" is worse than a false "да"."""
    from app.services.llm_client import chat, get_client

    if not get_client(cfg):
        return not bool(_NOT_LOOKING_HINT.search(text))

    try:
        raw = chat(
            cfg,
            [{"role": "user", "content": text}],
            system=(
                'Кандидат отвечает на вопрос рекрутера «Вы ещё в поиске работы?». '
                'Определи, ищет ли он всё ещё работу. Ответь ТОЛЬКО JSON: '
                '{"still_looking": true/false}'
            ),
            max_tokens=20,
            employee_id="quick_screening",
            employee_name="Быстрый режим (кандидаты)",
            feature="quick_screening",
        )
    except Exception as e:
        log.warning("quick_screening: interest-check LLM call failed: %s", e)
        return not bool(_NOT_LOOKING_HINT.search(text))

    if not raw:
        return not bool(_NOT_LOOKING_HINT.search(text))
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return not bool(_NOT_LOOKING_HINT.search(text))
    try:
        return bool(json.loads(m.group()).get("still_looking", True))
    except Exception:
        return not bool(_NOT_LOOKING_HINT.search(text))


def _format_answers(answers: list[dict]) -> str:
    lines = []
    for i, a in enumerate(answers, 1):
        lines.append(f"{i}. <b>{a.get('q', '')}</b>\n   → {a.get('a', '') or '—'}")
    return "\n".join(lines)


async def _handle_interest_reply(db, candidate, vacancy, src, token: str,
                                  state: dict, text: str, cfg: dict) -> None:
    """Reply to INTEREST_QUESTION, before the real quick_questions start."""
    from app.services.notify import send_notification

    # A counter-question here gets the same treatment as during the real
    # questions — stop and hand over rather than guess an answer.
    if _looks_like_question(text, cfg):
        state["status"] = "waiting_admin"
        state["reason"] = "question"
        save_state(db, candidate, state)
        await send_notification(
            f"❓ <b>Кандидат задал вопрос — нужен ваш ответ</b>\n"
            f"{_candidate_label(candidate, vacancy)}\n\n"
            f"Вопрос: «{text[:400]}»\n\nБот больше не пишет — отвечайте на площадке."
        )
        log.info("quick_screening: candidate %s asked a question during interest-check, handed to admin",
                  candidate.id)
        return

    if not _looks_still_interested(text, cfg):
        err = await _send(db, candidate, src, token, DECLINE_FAREWELL)
        if err:
            log.warning("quick_screening: failed to send farewell to candidate %s: %s", candidate.id, err)
        candidate.stage = "отказ"
        state["status"] = "done"
        save_state(db, candidate, state)
        await send_notification(
            f"🚫 <b>Кандидат больше не ищет работу</b>\n{_candidate_label(candidate, vacancy)}\n\n"
            f"Ответ: «{text[:200]}»\n\nЭтап переведён в «Отказ»."
        )
        log.info("quick_screening: candidate %s no longer looking, declined", candidate.id)
        return

    # Still looking — move on to the vacancy's real questions.
    questions = get_questions(vacancy)
    if not questions:
        state["status"] = "done"
        save_state(db, candidate, state)
        return

    err = await _send(db, candidate, src, token, questions[0])
    if err:
        state["status"] = "waiting_admin"
        state["reason"] = "send_failed"
        save_state(db, candidate, state)
        await send_notification(
            f"⚠️ <b>Не удалось задать первый вопрос</b>\n{_candidate_label(candidate, vacancy)}\n\nОшибка: {err}"
        )
        return

    state["phase"] = "questions"
    state["idx"] = 0
    state["asked_at"] = datetime.utcnow().isoformat()
    state["silence_alerted"] = False
    save_state(db, candidate, state)


async def handle_incoming(db, candidate, vacancy, src, token: str,
                           message_text: str, message_id: str, cfg: dict) -> None:
    """Process one incoming candidate message while a quick screen is running."""
    from app.services.notify import send_notification

    if candidate.is_paused:
        return  # ИИ-автоматизация на паузе — админ ведёт переписку вручную

    state = load_state(candidate)
    if not state or state.get("status") != "asking":
        return  # not screening (or already handed over) — nothing to do

    if message_id and state.get("last_msg_id") == message_id:
        return  # already processed this one
    state["last_msg_id"] = message_id or state.get("last_msg_id", "")

    text = (message_text or "").strip()
    if not text:
        save_state(db, candidate, state)
        return

    if state.get("phase", "questions") == "interest":
        await _handle_interest_reply(db, candidate, vacancy, src, token, state, text, cfg)
        return

    questions = get_questions(vacancy)
    idx = int(state.get("idx") or 0)
    if idx >= len(questions):
        state["status"] = "done"
        save_state(db, candidate, state)
        return

    # Counter-question → stop and hand over, without answering it.
    if _looks_like_question(text, cfg):
        state["status"] = "waiting_admin"
        state["reason"] = "question"
        # Кандидат мог в одном сообщении и ответить, и спросить («актуально,
        # а какая оплата?»). Раньше такой ответ терялся целиком — теперь он
        # записывается, и админ видит, на чём опрос остановился.
        answers = state.get("answers") or []
        idx = int(state.get("idx") or 0)
        if idx < len(questions):
            answers.append({"q": questions[idx], "a": text, "with_question": True})
            state["answers"] = answers
            state["idx"] = idx + 1
        save_state(db, candidate, state)
        collected = _format_answers(state.get("answers") or [])
        await send_notification(
            f"❓ <b>Кандидат задал вопрос — нужен ваш ответ</b>\n"
            f"{_candidate_label(candidate, vacancy)}\n\n"
            f"Вопрос: «{text[:400]}»\n\n"
            + (f"Успел ответить:\n{collected}\n\n" if collected else "")
            + "Бот больше не пишет — отвечайте на площадке."
        )
        log.info("quick_screening: candidate %s asked a question, handed to admin", candidate.id)
        return

    # Record the answer to the question currently pending.
    answers = state.get("answers") or []
    answers.append({"q": questions[idx], "a": text})
    state["answers"] = answers
    idx += 1
    state["idx"] = idx

    if idx < len(questions):
        err = await _send(db, candidate, src, token, questions[idx])
        if err:
            state["status"] = "waiting_admin"
            state["reason"] = "send_failed"
            save_state(db, candidate, state)
            await send_notification(
                f"⚠️ <b>Не удалось задать следующий вопрос</b>\n"
                f"{_candidate_label(candidate, vacancy)}\n\nОшибка: {err}"
            )
            return
        state["asked_at"] = datetime.utcnow().isoformat()
        state["silence_alerted"] = False
        save_state(db, candidate, state)
        return

    # All questions answered.
    state["status"] = "done"
    save_state(db, candidate, state)
    err = await _send(db, candidate, src, token, CLOSING_MESSAGE)
    if err:
        log.warning("quick_screening: failed to send closing message to candidate %s: %s", candidate.id, err)
    await send_notification(
        f"✅ <b>Кандидат ответил на все вопросы</b>\n{_candidate_label(candidate, vacancy)}\n\n"
        f"{_format_answers(answers)}\n\nДальше — вы."
    )
    log.info("quick_screening: completed for candidate_id=%s", candidate.id)


async def check_silence(db) -> None:
    """Alert once per candidate who has not answered the pending question for 24h."""
    from app.models.recruitment import Candidate, Vacancy
    from app.services.notify import send_notification

    now = datetime.utcnow()
    candidates = db.query(Candidate).filter(
        Candidate.quick_state_json.isnot(None),
        Candidate.quick_state_json != "",
    ).all()

    for c in candidates:
        if c.is_paused:
            continue
        state = load_state(c)
        if state.get("status") != "asking" or state.get("silence_alerted"):
            continue
        asked_at = state.get("asked_at")
        if not asked_at:
            continue
        try:
            asked_dt = datetime.fromisoformat(asked_at)
        except Exception:
            continue
        if now - asked_dt < SILENCE_AFTER:
            continue

        vacancy = db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first() if c.vacancy_id else None
        if state.get("phase", "questions") == "interest":
            pending = INTEREST_QUESTION
        else:
            questions = get_questions(vacancy)
            idx = int(state.get("idx") or 0)
            pending = questions[idx] if idx < len(questions) else ""
        collected = _format_answers(state.get("answers") or [])

        await send_notification(
            f"🔇 <b>Кандидат молчит сутки</b>\n{_candidate_label(c, vacancy)}\n\n"
            + (f"Ждём ответ на: «{pending}»\n\n" if pending else "")
            + (f"Успел ответить:\n{collected}\n\n" if collected else "")
            + "Бот больше не пишет."
        )
        state["silence_alerted"] = True
        save_state(db, c, state)
        log.info("quick_screening: silence alert for candidate_id=%s", c.id)
