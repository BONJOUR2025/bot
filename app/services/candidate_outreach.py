"""Сообщения кандидату, которые инициирует человек, а не бот.

Два случая, оба про один и тот же момент — рекрутёр разбирает воронку руками:

* **не дозвонился** — вместо того чтобы вслепую перезванивать, пишем в чат
  «когда вам удобно»; кандидат отвечает текстом, и следующий звонок уже по
  назначенному времени;
* **отказ** — кандидату уходит текст отказа, а не молчаливое исчезновение.

Почему это отдельный модуль, а не пара функций в роутере:

* отправка одинакова для hh и Авито, но адресуется по-разному (hh — по
  negotiation id, Авито — по chat id), и эта развилка не должна расползаться
  по вызывающим;
* расписание часов общения (candidate_hours) здесь намеренно **не**
  проверяется. Оно сдерживает автоматическую цепочку бота, а тут человек
  нажал кнопку и ждёт результата — молча придержать его сообщение до утра
  значило бы соврать интерфейсом. Раз рекрутёр работает в 21:00, писать в
  21:00 нормально;
* попытка дозвона фиксируется независимо от отправки: как раз тем, кому
  звонят, чата может не быть вовсе (отклик Авито «by_call» — только телефон),
  и терять из-за этого учёт звонков нельзя.
"""
from __future__ import annotations

import logging
from datetime import datetime

log = logging.getLogger(__name__)

DEFAULT_NO_ANSWER_MESSAGE = (
    "Здравствуйте! Пробовали до вас дозвониться, но не получилось. "
    "Подскажите, когда вам удобно поговорить?"
)

DEFAULT_REJECTION_MESSAGE = (
    "Здравствуйте! К сожалению, ваша кандидатура не подошла для данной вакансии. "
    "Спасибо за проявленный интерес, желаем удачи в поиске работы!"
)


def has_chat(candidate) -> bool:
    """Есть ли куда писать. Для Авито чат существует не всегда."""
    if candidate.source == "hh":
        return bool(candidate.external_id)
    if candidate.source == "avito":
        return bool((candidate.platform_chat_id or "").strip())
    return False


async def send_to_candidate(db, candidate, src, token: str, text: str) -> None:
    """Отправить сообщение в переписку на площадке и записать его в карточку.

    Бросает исключение площадки как есть: вызывающий показывает оператору,
    что именно пошло не так, — «отправлено» без отправки хуже ошибки.
    """
    from app.services import avito_api, hh_api, quick_screening

    text = (text or "").strip()
    if not text:
        raise ValueError("Пустой текст сообщения")

    if candidate.source == "avito":
        await avito_api.send_message(token, src.employer_id, candidate.platform_chat_id, text)
    else:
        await hh_api.send_message(token, candidate.external_id, text)

    quick_screening.record_last_message(db, candidate, text, "employer")


def register_call_attempt(db, candidate, *, now: datetime | None = None) -> int:
    """Записать неудачную попытку дозвона. Возвращает их общее число.

    Хранится в follow_up_count/follow_up_last_sent_at — колонках, оставшихся
    от вырезанной телеграм-воронки. Они пустые у всех кандидатов (проверено
    на боевой базе), а смысл «повторный контакт после неудачной попытки»
    совпадает, так что заводить ещё пару колонок того же назначения незачем.
    """
    candidate.follow_up_count = (candidate.follow_up_count or 0) + 1
    candidate.follow_up_last_sent_at = now or datetime.utcnow()
    db.commit()
    return candidate.follow_up_count


def reset_call_attempts(db, candidate) -> None:
    """Дозвонились — счётчик и флаг обнуляются."""
    candidate.follow_up_count = 0
    candidate.follow_up_last_sent_at = None
    db.commit()

# ─── Результат звонка ───────────────────────────────────────────────────────

OUTCOME_REACHED = "reached"
OUTCOME_NO_ANSWER = "no_answer"
OUTCOME_LATER = "later"
OUTCOME_INBOUND = "inbound"
OUTCOME_REJECTED = "rejected"

OUTCOMES = {OUTCOME_REACHED, OUTCOME_NO_ANSWER, OUTCOME_LATER,
            OUTCOME_INBOUND, OUTCOME_REJECTED}

# Исходящей попыткой считается ровно один результат. Ни входящий контакт, ни
# договорённость «перезвонить позже» попыткой не являются: правило «одна
# попытка в календарный день» опирается на факт нашего звонка, а не на любое
# касание карточки.
OUTBOUND_ATTEMPT_OUTCOMES = {OUTCOME_NO_ANSWER}


def _load_log(candidate) -> list:
    import json

    if not candidate.call_log_json:
        return []
    try:
        data = json.loads(candidate.call_log_json)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _save_log(candidate, entries: list) -> None:
    import json

    candidate.call_log_json = json.dumps(entries, ensure_ascii=False)


def record_outcome(db, candidate, outcome: str, *, call_hours=None,
                   now=None, next_at=None, message_sent: bool = False) -> dict:
    """Единая точка применения результата звонка.

    Через неё проходят все исходы — и из режима «Прозвон», и из карточки
    канбана (/no-answer, /reached). Смысл в том, чтобы правило следующего дня,
    журнал и снятие «ждёт ответа» не расползлись по вызывающим и не разошлись
    между двумя интерфейсами.

    Возвращает срез состояния для ответа API.
    """
    from app.services import call_queue
    from app.services import call_hours as call_hours_module
    from app.services.hours_window import LOCAL_UTC_OFFSET, local_now
    from app.services.recruitment_stages import STAGE_REJECTED

    if outcome not in OUTCOMES:
        raise ValueError(f"Неизвестный результат звонка: {outcome}")

    call_hours = call_hours or call_hours_module
    now_local = now or local_now()
    # follow_up_last_sent_at и last_inbound_handled_at живут в UTC, как и
    # остальные datetime модели; next_attempt_at — в локальном времени
    # (см. комментарий в модели). UTC выводится из локального, а не берётся
    # из utcnow() отдельно: иначе два времени одной операции разъезжаются,
    # и записанная попытка перестаёт попадать в тот календарный день, по
    # которому мы только что посчитали расписание.
    now_utc = now_local - LOCAL_UTC_OFFSET

    entry = {
        "at": now_utc.isoformat(timespec="seconds"),
        "outcome": outcome,
        # Снимок для отката: undo восстанавливает ровно то, что было до
        # результата, и ему негде взять эти значения, кроме журнала.
        "prev": {
            "follow_up_count": candidate.follow_up_count or 0,
            "follow_up_last_sent_at": (
                candidate.follow_up_last_sent_at.isoformat()
                if candidate.follow_up_last_sent_at else None
            ),
            "next_attempt_at": (
                candidate.next_attempt_at.isoformat()
                if candidate.next_attempt_at else None
            ),
            "last_inbound_handled_at": (
                candidate.last_inbound_handled_at.isoformat()
                if candidate.last_inbound_handled_at else None
            ),
            "stage": candidate.stage,
        },
    }
    if outcome == OUTCOME_NO_ANSWER:
        entry["message_sent"] = bool(message_sent)

    if outcome == OUTCOME_NO_ANSWER:
        candidate.follow_up_count = (candidate.follow_up_count or 0) + 1
        candidate.follow_up_last_sent_at = now_utc
        if call_queue.attempts_left(candidate):
            candidate.next_attempt_at = call_queue.next_allowed_call_time(
                now_local, call_hours)
        else:
            # Три попытки исчерпаны: кандидат уходит из очереди по флагу
            # no_contact, и назначать ему время больше незачем.
            candidate.next_attempt_at = None

    elif outcome == OUTCOME_REACHED:
        # Счётчик цикла обнуляется — контакт установлен. А вот отметку о
        # времени последнего звонка НЕ трогаем, в отличие от старой
        # reset_call_attempts: она держит вето «сегодня уже звонили», без
        # неё кандидат с обнулённым счётчиком тут же вернулся бы в очередь
        # как «ни разу не звонили». Журнал при этом сохраняет всю историю.
        candidate.follow_up_count = 0
        candidate.next_attempt_at = None

    elif outcome == OUTCOME_LATER:
        if next_at is None:
            raise ValueError("Для результата «перезвонить позже» нужно время")
        candidate.next_attempt_at = call_queue.normalize(
            next_at, candidate, call_hours, now=now_local)

    elif outcome == OUTCOME_INBOUND:
        # Кандидат вышел на связь сам. Это не наша исходящая попытка:
        # ни счётчик, ни follow_up_last_sent_at не трогаем — иначе входящий
        # контакт съедал бы дневной лимит звонков.
        candidate.next_attempt_at = None

    elif outcome == OUTCOME_REJECTED:
        candidate.stage = STAGE_REJECTED
        candidate.next_attempt_at = None

    # Любой результат звонка — это реакция на кандидата, в том числе на его
    # last_inbound_handled_at. Иначе сообщение, закрытое звонком, держало бы
    # карточку в «ждёт ответа» вечно: звонок мимо переписки не проходит.
    candidate.last_inbound_handled_at = now_utc

    entries = _load_log(candidate)
    entries.append(entry)
    _save_log(candidate, entries)
    db.commit()

    return {
        "id": candidate.id,
        "outcome": outcome,
        "call_attempts": candidate.follow_up_count or 0,
        "next_attempt_at": (
            candidate.next_attempt_at.isoformat()
            if candidate.next_attempt_at else None
        ),
        "no_contact": call_queue.no_contact(candidate),
        "stage": candidate.stage,
    }


def undo_last_outcome(db, candidate) -> dict:
    """Откатить последний результат.

    Возвращает состояние до него, снимая последнюю запись журнала. Отправленное
    кандидату сообщение НЕ отзывается — площадки этого не умеют, и делать вид,
    что откат полный, было бы враньём: вызывающий обязан предупредить оператора.
    """
    from datetime import datetime as _dt

    from app.services import call_queue

    entries = _load_log(candidate)
    if not entries:
        raise ValueError("Откатывать нечего — журнал пуст")

    last = entries.pop()
    prev = last.get("prev") or {}

    def _dt_or_none(raw):
        if not raw:
            return None
        try:
            return _dt.fromisoformat(raw)
        except Exception:
            return None

    candidate.follow_up_count = prev.get("follow_up_count") or 0
    candidate.follow_up_last_sent_at = _dt_or_none(prev.get("follow_up_last_sent_at"))
    candidate.next_attempt_at = _dt_or_none(prev.get("next_attempt_at"))
    candidate.last_inbound_handled_at = _dt_or_none(prev.get("last_inbound_handled_at"))
    if prev.get("stage"):
        candidate.stage = prev["stage"]

    _save_log(candidate, entries)
    db.commit()

    return {
        "id": candidate.id,
        "undone": last.get("outcome"),
        "call_attempts": candidate.follow_up_count or 0,
        "next_attempt_at": (
            candidate.next_attempt_at.isoformat()
            if candidate.next_attempt_at else None
        ),
        "no_contact": call_queue.no_contact(candidate),
        "stage": candidate.stage,
        # Сообщение уже ушло — предупредить оператора обязан вызывающий.
        "message_not_recalled": bool(last.get("message_sent")),
    }


def schedule_from_task(candidate_id: int, due_date, due_time) -> bool:
    """Перенесли задачу-звонок — подвинуть и расписание звонка.

    Задача и next_attempt_at — не дубликат друг друга: задача напоминает
    человеку, next_attempt_at решает, когда кандидат снова всплывёт в очереди.
    Разъехавшись, они дают ровно ту картину, из-за которой режим и появился:
    напоминание на четверг, а очередь предлагает звонить во вторник.

    Обратной синхронизации нет: УДАЛЕНИЕ задачи расписание не трогает —
    иначе случайно удалённое напоминание молча отменяло бы звонок.

    Возвращает True, если время кандидата изменилось.
    """
    from datetime import datetime as _dt
    from datetime import time as _time

    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate
    from app.services import call_hours, call_queue

    if not candidate_id or not due_date:
        return False

    # Время не указано — звоним с начала окна: «в четверг» без часа означает
    # рабочий день, а не полночь.
    wanted = _dt.combine(due_date, due_time or _time(0, 0))

    db = SessionLocal()
    try:
        c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not c:
            return False
        shifted = call_queue.normalize(wanted, c, call_hours)
        if c.next_attempt_at == shifted:
            return False
        c.next_attempt_at = shifted
        db.commit()
        return True
    finally:
        db.close()
