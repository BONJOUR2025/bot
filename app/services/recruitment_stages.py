"""Этапы найма и флаги состояния кандидата.

Единственный источник правды после того, как из системы убрали стратегии и
телеграм-интервью: остался только быстрый режим (app/services/quick_screening.py),
и воронка описывает ровно его.

Этап и флаги — намеренно разные вещи:

* **Этап** — позиция в воронке, движется только вперёд:
  новый → опрос → ответил → собеседование → нанят (или отказ).
  Первые три бот выставляет сам по ходу опроса, последние три ставит человек.
* **Флаги** — текущее состояние общения поверх этапа: «нужен ваш ответ»,
  «молчит», «не доставлено». Они не заменяют этап, потому что кандидат
  одновременно и «в опросе на 2 из 4», и «молчит третий день» — если сделать
  это одним полем, половина информации потеряется, а именно она и нужна,
  чтобы с одного взгляда понять, кто ждёт ответа.

Флаги нигде не хранятся: они вычисляются из quick_state в момент запроса,
поэтому не могут разойтись с реальным состоянием опроса.
"""
from __future__ import annotations

from datetime import datetime, timedelta

STAGE_NEW = "новый"
STAGE_SCREENING = "опрос"
STAGE_ANSWERED = "ответил"
STAGE_INTERVIEW = "собеседование"
STAGE_HIRED = "нанят"
STAGE_REJECTED = "отказ"

STAGES = [STAGE_NEW, STAGE_SCREENING, STAGE_ANSWERED,
          STAGE_INTERVIEW, STAGE_HIRED, STAGE_REJECTED]

# Этапы, которые ведёт бот по ходу опроса.
BOT_STAGES = {STAGE_NEW, STAGE_SCREENING, STAGE_ANSWERED}
# Этапы, которые ставит человек. Бот их не трогает никогда: если кандидата
# позвали на собеседование, дописанный им ответ не должен утащить карточку
# обратно в «опрос».
HUMAN_STAGES = {STAGE_INTERVIEW, STAGE_HIRED, STAGE_REJECTED}

FLAG_NEEDS_REPLY = "needs_reply"
FLAG_SILENT = "silent"
FLAG_UNDELIVERED = "undelivered"

SILENT_AFTER = timedelta(hours=24)


def derive_stage(current_stage: str | None, state: dict | None) -> str:
    """Этап кандидата по состоянию опроса.

    Человеческий этап всегда побеждает — см. HUMAN_STAGES.
    """
    if current_stage in HUMAN_STAGES:
        return current_stage

    state = state or {}
    status = state.get("status")
    answers = state.get("answers") or []

    if not status:
        return STAGE_NEW
    if status == "done":
        return STAGE_ANSWERED
    if status == "waiting_admin":
        # Не смогли отправить самый первый вопрос — опрос фактически не
        # начинался, кандидат так и остаётся новым (с флагом «не доставлено»).
        if state.get("reason") == "send_failed" and not answers:
            return STAGE_NEW
        return STAGE_SCREENING
    return STAGE_SCREENING


def progress(state: dict | None, questions: list[str] | None) -> dict:
    """Сколько вопросов из скольких кандидат уже прошёл."""
    state = state or {}
    return {
        "answered": len(state.get("answers") or []),
        "total": len(questions or []),
    }


def _silent_days(state: dict, now: datetime) -> int | None:
    asked_at = state.get("asked_at")
    if not asked_at:
        return None
    try:
        asked_dt = datetime.fromisoformat(asked_at)
    except Exception:
        return None
    idle = now - asked_dt
    if idle < SILENT_AFTER:
        return None
    return max(1, idle.days)


def flags(state: dict | None, *, now: datetime | None = None) -> list[dict]:
    """Флаги состояния: что именно сейчас требует внимания.

    Каждый флаг — {"code", "label"}, чтобы список рендерился без словаря
    подписей на фронте и подпись оставалась одинаковой везде, включая
    уведомления.
    """
    state = state or {}
    now = now or datetime.utcnow()
    status = state.get("status")
    result: list[dict] = []

    if status == "waiting_admin":
        if state.get("reason") == "send_failed":
            result.append({"code": FLAG_UNDELIVERED, "label": "не доставлено"})
        else:
            result.append({"code": FLAG_NEEDS_REPLY, "label": "нужен ваш ответ"})

    if status == "asking":
        days = _silent_days(state, now)
        if days is not None:
            result.append({
                "code": FLAG_SILENT,
                "label": f"молчит {days} дн." if days > 1 else "молчит сутки",
                "days": days,
            })

    return result


# Старые этапы → новые. Всё, что было про телеграм-воронку («ждем_привязки»,
# «общение», «ждем»), схлопывается в «новый»: привязки к телеграму больше нет,
# и эти кандидаты просто ждут опроса на площадке.
LEGACY_STAGE_MAP = {
    "отклик": STAGE_NEW,
    "ждем": STAGE_NEW,
    "ждем_привязки": STAGE_NEW,
    "общение": STAGE_NEW,
    "собеседование": STAGE_INTERVIEW,
    "нанят": STAGE_HIRED,
    "отказ": STAGE_REJECTED,
}
