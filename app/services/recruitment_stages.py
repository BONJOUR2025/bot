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
# Дозвонились, поговорили — кандидат взял паузу на подумать. Отдельный этап,
# потому что иначе такие висят в «Ответил» вперемешку с теми, кому ещё не
# звонили, и прозвон приходится начинать с попытки вспомнить, с кем уже
# говорили.
STAGE_THINKING = "думает"
STAGE_INTERVIEW = "собеседование"
STAGE_HIRED = "нанят"
STAGE_REJECTED = "отказ"
# Отстойник для условно мёртвых: организации, случайные чаты, отклики
# двухлетней давности. Не «отказ» — отказ означает решение по человеку, а
# здесь мы просто убираем с глаз то, что кандидатом никогда не было.
#
# Именно перемещением, а не удалением: карточка остаётся ключом, по которому
# импорт узнаёт уже виденного человека. Удалить — значит получить их всех
# заново при следующей переnastройке интеграции, что однажды уже случилось.
STAGE_RESERVE = "резерв"

STAGES = [STAGE_NEW, STAGE_SCREENING, STAGE_ANSWERED, STAGE_THINKING,
          STAGE_INTERVIEW, STAGE_HIRED, STAGE_REJECTED, STAGE_RESERVE]

# Этапы, на которых работа с человеком закончена: ни опроса, ни ответов, ни
# уведомлений. Один список на всех, кто это проверяет, — раньше терминальные
# этапы перечисляли по месту, и «резерв» пришлось бы не забыть дописать в
# каждое из них.
TERMINAL_STAGES = [STAGE_HIRED, STAGE_REJECTED, STAGE_RESERVE]

# Этапы, которые ведёт бот по ходу опроса.
BOT_STAGES = {STAGE_NEW, STAGE_SCREENING, STAGE_ANSWERED}
# Этапы, которые ставит человек. Бот их не трогает никогда: если кандидата
# позвали на собеседование, дописанный им ответ не должен утащить карточку
# обратно в «опрос». «Думает» здесь по той же причине и с большим весом:
# кандидат на этом этапе как раз и должен написать «я согласен», и этот
# ответ обязан оставить карточку на месте, а не сбросить её в «опрос».
HUMAN_STAGES = {STAGE_THINKING, STAGE_INTERVIEW, STAGE_HIRED, STAGE_REJECTED,
                STAGE_RESERVE}

FLAG_NEEDS_REPLY = "needs_reply"
FLAG_SILENT = "silent"
FLAG_UNDELIVERED = "undelivered"
FLAG_NO_ANSWER = "no_answer"
# Три попытки исчерпаны. Это НЕ этап воронки: решения по человеку мы не
# приняли, просто не смогли до него дозвониться. Отдельный этап добавил бы
# восьмую колонку в канбан, а флаг рисуется на карточке — механизм уже есть.
FLAG_NO_CONTACT = "no_contact"
# Кандидат написал последним и ждёт нашего ответа в переписке. Отдельно от
# звонков: такому кандидату нужно ответить текстом, а не набирать номер.
FLAG_AWAITING_REPLY = "awaiting_reply"

SILENT_AFTER = timedelta(hours=24)

# Сколько неудачных дозвонов до того, как карточка начнёт требовать решения
# (перезванивать четвёртый раз бессмысленно — нужен либо отказ, либо пауза).
NO_ANSWER_ESCALATE_AT = 3


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


def _no_answer_label(count: int, last_at: datetime | None, now: datetime) -> str:
    base = "не дозвонился" if count == 1 else f"не дозвонился ×{count}"
    if not last_at:
        return base
    idle = now - last_at
    if idle < timedelta(hours=1):
        return f"{base}, только что"
    if idle < timedelta(days=1):
        return f"{base}, {max(1, int(idle.total_seconds() // 3600))} ч назад"
    return f"{base}, {idle.days} дн. назад"


def flags(state: dict | None, *, now: datetime | None = None,
          call_attempts: int = 0, last_call_at: datetime | None = None,
          awaiting_reply: bool = False) -> list[dict]:
    """Флаги состояния: что именно сейчас требует внимания.

    Каждый флаг — {"code", "label"}, чтобы список рендерился без словаря
    подписей на фронте и подпись оставалась одинаковой везде, включая
    уведомления.

    Недозвоны приходят отдельными аргументами, а не через объект кандидата:
    модуль описывает воронку и намеренно ничего не знает про SQLAlchemy —
    иначе его нельзя было бы посчитать на голых данных в тестах.
    """
    state = state or {}
    now = now or datetime.utcnow()
    status = state.get("status")
    result: list[dict] = []

    if awaiting_reply:
        result.append({"code": FLAG_AWAITING_REPLY, "label": "ждёт ответа"})

    if call_attempts and call_attempts > 0:
        exhausted = call_attempts >= NO_ANSWER_ESCALATE_AT
        result.append({
            # Исчерпанные попытки — это уже не «не дозвонился в очередной
            # раз», а состояние «не вышел на связь»: звонить больше не будем.
            "code": FLAG_NO_CONTACT if exhausted else FLAG_NO_ANSWER,
            "label": ("не вышел на связь" if exhausted
                      else _no_answer_label(call_attempts, last_call_at, now)),
            "attempts": call_attempts,
            # Подсказка интерфейсу: пора не звонить снова, а решать.
            "escalate": exhausted,
        })

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
