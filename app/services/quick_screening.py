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
  counter-question           → record the answer it came with, stop asking,
                               alert, stay silent (do NOT answer it); on the
                               LAST question the screen still completes — the
                               profile is built and the alert carries it
  silent for 24h             → alert

State lives in Candidate.quick_state_json:
  {"status": "asking"|"waiting_admin"|"done",
   "phase": "interest"|"questions",  # "вы ещё в поиске?" vs the real questions;
                                      # absent (legacy rows) means "questions"
   "idx": int,                       # index of the question awaiting an answer
   "answers": [{"q": str, "a": str}],
   "completed": bool,                # вопросы дошли до конца (независимо от status)
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

# Классификаторы ниже отвечают одним булевым значением по одной короткой
# реплике — здесь нужна не «живость», а повторяемость: один и тот же текст
# обязан давать один и тот же ответ.
#
# Ни того, ни другого не было. Вызовы шли на дефолтную модель конфига
# (openai/gpt-4.1-nano) и без temperature, и на коротких ответах результат
# плавал: «Да, есть !», «Да ..присматриваюсь пока...» и «Да, удобно, я живу
# на Новочеркасской» при семи прогонах подряд каждый раз давали и True, и
# False. 04.09.2026 на этом Свиридова (#272), ответившая «Да» на последний
# вопрос, была разобрана как задавшая встречный вопрос: опрос оборвался в
# шаге от конца. Ошибка работает и в обратную сторону — «Вы закрыли
# объявление, вы нашли уже сотрудников ?» распознавалось как вопрос лишь в
# трёх прогонах из семи.
#
# Та же связка (модель побольше + temperature=0) уже вылечила разброс
# оценок в candidate_profile.py — см. комментарий к MODEL там.
MODEL = "openai/gpt-4.1"

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

# Явный вопрос: вопросительное слово И знак вопроса одновременно.
#
# Нужен потому, что модель на коротких фразах плавает: «Какая цена за
# изделие?» при пяти прогонах подряд дала True, False, False, True, True.
# Здесь важна несимметричность цены ошибки. Пропущенный встречный вопрос
# означает, что живой кандидат остался без ответа — это мы уже наблюдали:
# Захаренкова с 21 годом стажа спросила «или я общаюсь с ботом?» и ждала
# двое суток. Лишнее срабатывание означает лишь, что разговор чуть раньше
# передали человеку, а это и есть желаемый исход.
#
# Требование обоих признаков сразу, а не одного «?», отсекает ответы вида
# «Да?» и обычные реплики со знаком вопроса в конце.
_OBVIOUS_QUESTION = re.compile(
    r"(?=.*\?)"
    r"(?=.*\b(сколько|какая|какие|какой|каков|когда|где|почему|зачем|"
    r"можно ли|есть ли|подскажите|расскажите|уточните)\b)",
    re.IGNORECASE | re.DOTALL,
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


# Заявление «я уже трудоустроен» посреди опроса. Отдельно от
# _NOT_LOOKING_HINT: тот проверяет ОТВЕТ на прямой вопрос «вы ещё в поиске?»,
# где голое «нет» — это отказ. Здесь же кандидат отвечает на «На каких
# позициях работали?», и «нет» означает «нет такого опыта», а не «не ищу».
# Поэтому голого отрицания недостаточно, нужно именно заявление.
_ALREADY_EMPLOYED_HINT = re.compile(
    r"уже\s*наш[её]л|уже\s*нашла|уже\s*устро|нашл[аи]?\s*работу|"
    r"не\s*актуальн|неактуальн|вышел\s*на\s*работу|closed|"
    r"больше\s*не\s*ищу|не\s*ищу\s*работу",
    re.IGNORECASE,
)


def _announces_not_looking(text: str, cfg: dict) -> bool:
    """Кандидат посреди опроса сообщает, что уже трудоустроен.

    Найдено в переписках: Халимов на вопрос о позициях ответил «Здравствуйте
    я уже устроился» и получил в ответ следующий вопрос по списку. Осипов —
    «Спасибо, я уже нашел», и тоже поехали дальше. Проверка интереса
    вызывалась только в первой фазе, а человек может передумать в любой.

    Асимметрия здесь ОБРАТНАЯ той, что у встречного вопроса: попрощаться с
    заинтересованным кандидатом дороже, чем задать лишний вопрос уже
    трудоустроенному. Поэтому срабатываем, только когда И ключевые слова, И
    модель согласны; при любой неуверенности продолжаем опрос.

    Ключевые слова заодно работают предфильтром: без них модель не
    вызывается вовсе, так что на обычных ответах это ничего не стоит.
    """
    if not _ALREADY_EMPLOYED_HINT.search(text or ""):
        return False

    from app.services.llm_client import chat, get_client

    if not get_client(cfg):
        return True  # ключевые слова здесь достаточно однозначны

    try:
        raw = chat(
            cfg,
            [{"role": "user", "content": text}],
            system=(
                "Сообщение кандидата в переписке о вакансии. Определи, сообщает ли он, "
                "что уже нашёл работу или больше не ищет. Ответь ТОЛЬКО JSON: "
                '{"not_looking": true/false}'
            ),
            max_tokens=20,
            model=MODEL,
            temperature=0,
            employee_id="quick_screening",
            employee_name="Быстрый режим (кандидаты)",
            feature="quick_screening",
        )
    except Exception as e:
        log.warning("quick_screening: not-looking check failed: %s", e)
        return True

    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return True
    try:
        return bool(json.loads(m.group()).get("not_looking"))
    except Exception:
        return True


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

    from app.services import candidate_hours

    if candidate.is_paused:
        return False  # ИИ-автоматизация поставлена на паузу для этого кандидата
    questions = get_questions(vacancy)
    if not questions:
        return False
    if load_state(candidate):
        return False  # already started

    if not candidate_hours.is_within():
        # Отклик пришёл ночью — здороваться сейчас нельзя. Ставим опрос в
        # очередь: status="queued" отличает «ждёт рабочих часов» от «идёт»
        # и от «не запускался», и переживает перезапуск, потому что лежит
        # в БД. Стартует flush_deferred в начале ближайшего окна.
        save_state(db, candidate, {
            "status": "queued", "phase": "interest", "idx": 0, "answers": [],
            "asked_at": None, "last_msg_id": "", "silence_alerted": False,
            "queued_at": datetime.utcnow().isoformat(),
        })
        log.info("quick_screening: candidate %s arrived outside working hours, screening queued",
                 candidate.id)
        return False

    # Уведомления «бот начал опрос» здесь намеренно нет: их приходило по
    # шесть в сутки, и ни одно не требовало действия — бот как раз работает
    # сам, а новый отклик и так виден в воронке. Ровно такие сообщения
    # приучали пролистывать ленту не читая, из-за чего терялись те, где
    # кандидат действительно ждал ответа.

    greeting = f"Здравствуйте!\n\n{INTEREST_QUESTION}"
    err = await _send(db, candidate, src, token, greeting)
    if err:
        log.warning("quick_screening: failed to send greeting to candidate %s: %s", candidate.id, err)
        await send_notification(
            f"🛠 <b>СБОЙ · Не удалось написать кандидату</b>\n{_candidate_label(candidate, vacancy)}\n\n"
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

    # Явный вопрос не отдаём модели на суд вовсе: она на таких коротких
    # фразах недетерминирована, а ошибка здесь стоит живого кандидата.
    if _OBVIOUS_QUESTION.search(text):
        return True

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
            model=MODEL,
            temperature=0,
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
            model=MODEL,
            temperature=0,
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
            f"🔴 <b>НУЖЕН ОТВЕТ · Вопрос от кандидата</b>\n"
            f"{_candidate_label(candidate, vacancy)}\n\n"
            f"«{text[:400]}»\n\nБот больше не пишет — отвечайте на площадке."
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
        # Уведомления здесь намеренно нет: бот попрощался и перевёл карточку
        # в «Отказ» сам, действия от человека не требуется, а сам факт виден
        # в воронке. В ленте это было чистым шумом.
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
            f"🛠 <b>СБОЙ · Не удалось задать первый вопрос</b>\n{_candidate_label(candidate, vacancy)}\n\nОшибка: {err}"
        )
        return

    state["phase"] = "questions"
    state["idx"] = 0
    state["asked_at"] = datetime.utcnow().isoformat()
    state["silence_alerted"] = False
    save_state(db, candidate, state)


async def handle_incoming(db, candidate, vacancy, src, token: str,
                           message_text: str, message_id: str, cfg: dict) -> None:
    """Process one incoming candidate message while a quick screen is running.

    Вне рабочих часов ответ не обрабатывается, а откладывается: см.
    app/services/candidate_hours.py. Откладывается именно входящее сообщение
    целиком, а не «следующее действие» — тогда при наступлении окна
    отыгрывается ровно та же логика (встречный вопрос, проверка интереса,
    завершение), а не её копия, которая неизбежно разъедется с оригиналом.
    """
    from app.services import candidate_hours

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

    if not candidate_hours.is_within(cfg=cfg):
        # last_msg_id уже проставлен выше — значит ни опрос, ни вебхук не
        # положат это сообщение второй раз, а сам текст лежит в состоянии и
        # переживёт перезапуск. Дальше его доиграет flush_deferred.
        state["deferred_incoming"] = {
            "text": text,
            "message_id": message_id or "",
            "received_at": datetime.utcnow().isoformat(),
        }
        save_state(db, candidate, state)
        record_last_message(db, candidate, text, "applicant")
        log.info("quick_screening: candidate %s replied outside working hours, deferred", candidate.id)
        return

    await _process_message(db, candidate, vacancy, src, token, state, text, cfg)


async def _process_message(db, candidate, vacancy, src, token: str,
                            state: dict, text: str, cfg: dict) -> None:
    """Собственно обработка ответа кандидата — без дедупа и без проверки
    рабочих часов: то же самое проигрывается и «сейчас», и отложенно."""
    from app.services import candidate_profile
    from app.services.notify import send_notification

    if state.get("phase", "questions") == "interest":
        await _handle_interest_reply(db, candidate, vacancy, src, token, state, text, cfg)
        return

    questions = get_questions(vacancy)
    idx = int(state.get("idx") or 0)
    if idx >= len(questions):
        state["status"] = "done"
        save_state(db, candidate, state)
        return

    # «Я уже устроился» посреди опроса — прощаемся, а не задаём следующий
    # вопрос. Проверка интереса раньше жила только в первой фазе, и человек,
    # передумавший на середине, продолжал получать анкету: Халимову после
    # «Здравствуйте я уже устроился» пришло «На каких позициях вы работали?».
    if _announces_not_looking(text, cfg):
        err = await _send(db, candidate, src, token, DECLINE_FAREWELL)
        if err:
            log.warning("quick_screening: failed to send farewell to candidate %s: %s", candidate.id, err)
        candidate.stage = "отказ"
        state["status"] = "done"
        state["reason"] = "not_looking"
        save_state(db, candidate, state)
        # Уведомления нет — см. соседний случай в _handle_interest_reply:
        # бот закрыл вопрос сам.
        log.info("quick_screening: candidate %s announced they are employed mid-screen, declined",
                 candidate.id)
        return

    # Встречный вопрос считаем здесь, а решение откладываем до того момента,
    # когда ответ записан и видно, остались ли вопросы.
    #
    # Раньше проверка стояла первой и обрывала опрос немедленно — в том числе
    # на последнем ответе, когда спрашивать больше нечего. Анкета была собрана
    # целиком, но кандидат оставался без завершающего сообщения, а карточка — без
    # сводки: к 04.09.2026 таких накопилось десять, у пятерых сводки не было
    # вовсе. Пройденный опрос — это пройденный опрос, что бы ни было в последней
    # реплике.
    asked_back = _looks_like_question(text, cfg)

    # Ответ записываем всегда: кандидат мог в одном сообщении и ответить, и
    # спросить («актуально, а какая оплата?»).
    answers = state.get("answers") or []
    entry = {"q": questions[idx], "a": text}
    if asked_back:
        entry["with_question"] = True
    answers.append(entry)
    state["answers"] = answers
    idx += 1
    state["idx"] = idx

    if idx < len(questions):
        # Вопросы ещё остались. Встречный вопрос здесь означает то же, что и
        # раньше: перестаём спрашивать и зовём человека, не пытаясь ответить сами.
        if asked_back:
            state["status"] = "waiting_admin"
            state["reason"] = "question"
            save_state(db, candidate, state)
            await send_notification(
                f"🔴 <b>НУЖЕН ОТВЕТ · Вопрос от кандидата</b>\n"
                f"{_candidate_label(candidate, vacancy)}\n\n"
                f"«{text[:400]}»\n\n"
                f"Успел ответить:\n{_format_answers(answers)}\n\n"
                "Бот больше не пишет — отвечайте на площадке."
            )
            log.info("quick_screening: candidate %s asked a question, handed to admin", candidate.id)
            return

        err = await _send(db, candidate, src, token, questions[idx])
        if err:
            state["status"] = "waiting_admin"
            state["reason"] = "send_failed"
            save_state(db, candidate, state)
            await send_notification(
                f"🛠 <b>СБОЙ · Не удалось задать следующий вопрос</b>\n"
                f"{_candidate_label(candidate, vacancy)}\n\nОшибка: {err}"
            )
            return
        state["asked_at"] = datetime.utcnow().isoformat()
        state["silence_alerted"] = False
        save_state(db, candidate, state)
        return

    # Вопросы кончились — анкета собрана. Встречный вопрос в последней
    # реплике меняет только одно: разговор переходит к человеку, а не закрывается.
    #
    # completed — факт о том, что произошло, а не статус разговора. Он нужен
    # воронке: без него карточка с waiting_admin читалась как «опрос идёт» даже
    # тогда, когда отвечено всё, и возвращалась в «Опрос» после каждого
    # обновления страницы. Статус говорит, кто ведёт разговор сейчас, а
    # этап — как далеко человек прошёл; смешивать их нельзя.
    state["status"] = "waiting_admin" if asked_back else "done"
    state["completed"] = True
    if asked_back:
        state["reason"] = "question"
    save_state(db, candidate, state)

    # Завершающее «мы свяжемся с вами» уместно только когда кандидат ни о чём
    # не спросил: в ответ на прямой вопрос оно читается как отписка.
    if not asked_back:
        err = await _send(db, candidate, src, token, CLOSING_MESSAGE)
        if err:
            log.warning("quick_screening: failed to send closing message to candidate %s: %s", candidate.id, err)

    # Сводка по ответам и анкете с площадки. Строго после того, как опрос
    # закрыт и кандидату отправлено прощание: это подпись к карточке, и её
    # отсутствие не должно ни задерживать, ни ломать сам опрос.
    profile = None
    try:
        profile = candidate_profile.generate(db, candidate, vacancy, answers, cfg)
    except Exception:
        log.warning("quick_screening: не удалось собрать сводку по кандидату %s",
                    candidate.id, exc_info=True)

    summary = candidate_profile.format_for_notification(profile)
    await send_notification(
        (f"🔴 <b>НУЖЕН ОТВЕТ · Анкета готова, есть вопрос от кандидата</b>"
         if asked_back else "🔴 <b>НУЖЕН ОТВЕТ · Анкета готова</b>")
        + f"\n{_candidate_label(candidate, vacancy)}\n\n"
        + (f"«{text[:400]}»\n\n" if asked_back else "")
        + f"{_format_answers(answers)}\n\n"
        + (f"{summary}\n\n" if summary else "")
        + ("Бот больше не пишет — отвечайте на площадке." if asked_back
           else "Дальше — вы.")
    )
    log.info("quick_screening: completed for candidate_id=%s (встречный вопрос: %s)",
             candidate.id, asked_back)


async def flush_deferred(db, resolve_source) -> int:
    """Доиграть то, что отложено на нерабочее время. Возвращает число
    обработанных кандидатов.

    Вызывается периодически и при старте процесса — именно это и делает
    механику устойчивой к падению: всё отложенное лежит в quick_state_json,
    поэтому после перезапуска цепочка продолжается с того места, где
    остановилась, а не начинается заново.

    resolve_source(source) → (src, token) | None — резолвер площадки,
    передаётся снаружи, чтобы этот модуль не знал про устройство синка.
    """
    from app.models.recruitment import Candidate, Vacancy
    from app.services import candidate_hours
    from app.services.config_service import ConfigService

    if not candidate_hours.is_within():
        return 0

    candidates = db.query(Candidate).filter(
        Candidate.quick_state_json.isnot(None),
        Candidate.quick_state_json != "",
    ).all()

    pending = []
    for c in candidates:
        if c.is_paused:
            continue
        state = load_state(c)
        if state.get("status") == "queued" or state.get("deferred_incoming"):
            pending.append(c)
    if not pending:
        return 0

    cfg = ConfigService().load()
    processed = 0
    for c in pending:
        try:
            resolved = resolve_source(c.source)
            if not resolved:
                continue
            src, token = resolved
            vacancy = db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first() if c.vacancy_id else None
            state = load_state(c)

            if state.get("status") == "queued":
                # Опрос ещё не начинался — стартуем с чистого листа. Состояние
                # очереди снимаем до вызова, иначе start_screening увидит его
                # как «уже запущен» и ничего не сделает.
                c.quick_state_json = None
                db.commit()
                await start_screening(db, c, vacancy, src, token)
                processed += 1
                continue

            deferred = state.pop("deferred_incoming", None)
            if not deferred:
                continue
            # Снимаем отложенное ДО обработки: если обработка упадёт на
            # середине, кандидат не должен попасть в вечный цикл повторов —
            # ответ уже записан в переписке, а админ увидит его в карточке.
            save_state(db, c, state)
            await _process_message(db, c, vacancy, src, token, state,
                                    deferred.get("text", ""), cfg)
            processed += 1
            log.info("quick_screening: replayed deferred reply for candidate %s", c.id)
        except Exception:
            log.warning("quick_screening: failed to flush deferred for candidate %s",
                        c.id, exc_info=True)
    return processed


async def check_silence(db) -> None:
    """Alert once per candidate who has not answered the pending question for 24h."""
    from app.models.recruitment import Candidate, Vacancy
    from app.services.notify import send_notification

    now = datetime.utcnow()
    silent: list[str] = []
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

        # Копим и отправляем одним сообщением ниже: молчащих за сутки бывает
        # сразу несколько, и три подряд одинаковых уведомления — ровно тот
        # шум, из-за которого лента перестаёт читаться.
        silent.append(f"• {_candidate_label(c, vacancy)}"
                      + (f" — ждём ответ на «{pending[:60]}»" if pending else ""))
        state["silence_alerted"] = True
        save_state(db, c, state)
        log.info("quick_screening: silence alert for candidate_id=%s", c.id)

    if silent:
        await send_notification(
            f"⚪ <b>Молчат сутки — {len(silent)}</b>\n\n"
            + "\n".join(silent)
            + "\n\nБот им больше не пишет."
        )
