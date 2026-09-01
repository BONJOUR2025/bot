"""Очередь исходящих звонков — режим «Прозвон».

Очередь не хранится. Она вычисляется предикатом в момент запроса, ровно как
этап кандидата вычисляется из состояния опроса (recruitment_stages.derive_stage):
хранимый флаг «в очереди» пришлось бы синхронизировать при каждом изменении
кандидата, и однажды он бы соврал. Отсюда же следует, что фоновых задач у режима
нет вообще: наступление next_attempt_at — это сравнение с now внутри запроса,
класть кандидата в очередь некому и незачем.

Модуль намеренно ничего не знает про SQLAlchemy: он принимает объект кандидата
и расписание, а не сессию, — поэтому считается на голых данных и тестируется
без базы. Тот же приём, что в recruitment_stages.

ГЛАВНОЕ ПРАВИЛО. Одна исходящая попытка в календарный день — это не одно из
условий доступности, а ВЕТО: called_today() перекрывает next_attempt_at, время,
названное самим кандидатом, и любые входящие сообщения. Проверка стоит раньше
due() именно поэтому. Единственный способ позвонить второй раз за день —
осознанное ручное действие человека из карточки канбана; автоматическая очередь
второй звонок не предлагает никогда.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.services.recruitment_stages import (
    NO_ANSWER_ESCALATE_AT,
    STAGE_ANSWERED,
    STAGE_NEW,
    TERMINAL_STAGES,
)
from app.services.hours_window import local_now, to_local

# Этапы, с которых кандидату вообще может понадобиться звонок.
#
# «ответил» — опрос пройден, дальше по процессу звонок. «новый» нужен для
# вакансий с выключенным быстрым режимом: там опроса не будет никогда, и
# ждать перехода в «ответил» бессмысленно — это условие проверяется отдельно,
# по самой вакансии (см. queue_stage_allowed).
QUEUE_STAGES = {STAGE_ANSWERED, STAGE_NEW}

# Причины попадания в очередь — для подписи «почему сейчас» в интерфейсе.
REASON_SCHEDULED = "scheduled"      # наступило назначенное время
REASON_NEVER_CALLED = "never_called"  # ни разу не звонили
REASON_RETRY = "retry"              # повторная попытка, день прошёл

PRIORITY_SCHEDULED = 1
PRIORITY_NEVER_CALLED = 2
PRIORITY_RETRY = 3


# ── входящие ─────────────────────────────────────────────────────────────

def unhandled_inbound(c) -> bool:
    """Кандидат написал последним, и мы ещё не отреагировали.

    Основной сигнал уже есть в модели и поддерживается сам: last_message_from
    переключается на "employer" при любой нашей отправке (см. вызовы
    quick_screening.record_last_message), поэтому ответ в чат снимает признак
    без всякой ручной отметки.

    Второй признак нужен потому, что звонок идёт мимо переписки: позвонив, мы
    в чат не пишем, last_message_from остаётся "applicant", и без
    last_inbound_handled_at кандидат навсегда завис бы в «ждёт ответа».
    Поэтому любой результат звонка проставляет эту отметку.
    """
    if getattr(c, "last_message_from", None) != "applicant":
        return False
    last_at = getattr(c, "last_message_at", None)
    if not last_at:
        return False
    handled = getattr(c, "last_inbound_handled_at", None)
    return handled is None or handled < last_at


# ── правило одной попытки в день ─────────────────────────────────────────

def called_today(c, now: datetime | None = None) -> bool:
    """Была ли сегодня исходящая попытка.

    Единственный источник — follow_up_last_sent_at, который пишется только
    в candidate_outreach.record_outcome и только для исхода no_answer
    (см. OUTBOUND_ATTEMPT_OUTCOMES), то есть строго по факту нашего звонка.
    Входящие контакты его не трогают.

    Граница календарного дня — ЛОКАЛЬНАЯ. Поле хранится в UTC
    (datetime.utcnow), а окно звонков задано в локальных часах: сравнивая
    напрямую, мы бы каждую ночь ошибались на три часа — звонок в 01:30 по
    локальному времени считался бы вчерашним.
    """
    last = getattr(c, "follow_up_last_sent_at", None)
    if not last:
        return False
    now = now or local_now()
    return to_local(last).date() == now.date()


# Исходы, после которых кандидат на сегодня закрыт: разговор состоялся либо
# человек вышел на связь сам. «Перезвонить позже» сюда НЕ входит — назначенное
# на сегодняшний вечер время должно сработать сегодня же; «недозвон» тоже нет —
# его держит вето called_today по факту исходящей попытки.
CLOSING_OUTCOMES = ("reached", "inbound")


def handled_today(c, now: datetime | None = None) -> bool:
    """Сегодня по кандидату уже приняли закрывающий результат.

    Нужно потому, что «Дозвонился» обнуляет follow_up_count и next_attempt_at —
    а это ровно сигнатура корзины «ни разу не звонили». Без этой проверки
    рекрутер нажимал «Дозвонился» и получал того же человека снова: очередь
    честно считала, что звонить ему ещё не начинали.

    Источник — журнал контактов, уже существующий и append-only. Ни одно поле
    счётчиков при этом не меняет смысла: called_today по-прежнему отвечает
    только за исходящие попытки, а эта функция — за «с человеком на сегодня
    закончили».
    """
    now = now or local_now()
    today = now.date()
    for entry in _log(c):
        if entry.get("outcome") not in CLOSING_OUTCOMES:
            continue
        at = _entry_time(entry)
        if at and to_local(at).date() == today:
            return True
    return False


def calls_made_today(c, now: datetime | None = None) -> int:
    """Сколько исходящих звонков сделано этому кандидату сегодня.

    Считается по журналу, а не по follow_up_last_sent_at: успешный звонок
    поле недозвонов не трогает (и не должен), но в счётчике «звонков сегодня»
    он обязан быть — иначе день, проведённый на удачных звонках, показывает
    ноль.
    """
    now = now or local_now()
    today = now.date()
    made = 0
    for entry in _log(c):
        # Исходящий звонок — это недозвон и состоявшийся разговор. Входящий
        # контакт и договорённость о переносе звонком не являются.
        if entry.get("outcome") not in ("no_answer", "reached"):
            continue
        at = _entry_time(entry)
        if at and to_local(at).date() == today:
            made += 1
    return made


def _log(c) -> list:
    raw = getattr(c, "call_log_json", None)
    if not raw:
        return []
    try:
        import json

        data = json.loads(raw)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _entry_time(entry: dict) -> datetime | None:
    """Момент записи журнала. Хранится в UTC (см. record_outcome)."""
    try:
        return datetime.fromisoformat(entry.get("at"))
    except (TypeError, ValueError):
        return None


def next_allowed_call_time(after: datetime, call_hours) -> datetime | None:
    """Ближайший допустимый момент СЛЕДУЮЩЕГО дня.

    Не after + 24h: сутки от полудня упираются в полдень следующего дня, а
    от позднего вечера — в ночь. Берём начало ближайшего окна звонков строго
    со следующего календарного дня.
    """
    tomorrow: date = after.date() + timedelta(days=1)
    return call_hours.window_start_on_or_after(tomorrow)


def normalize(wanted: datetime, c, call_hours, now: datetime | None = None) -> datetime:
    """Самый ранний момент, когда звонок этому кандидату вообще возможен.

    Учитывает оба ограничения: вето «сегодня уже звонили» и окно звонков.
    Именно поэтому названное кандидатом «позвоните сегодня в 18:00» после
    состоявшегося сегодня недозвона превращается в следующий допустимый день,
    а не в сегодняшние 18:00.
    """
    now = now or local_now()
    earliest = wanted
    if called_today(c, now):
        floor = next_allowed_call_time(now, call_hours)
        if floor and floor > earliest:
            earliest = floor
    return call_hours.shift_into_window(earliest)


# ── предикат очереди ─────────────────────────────────────────────────────

def due(c, now: datetime | None = None) -> bool:
    """Наступила ли нижняя граница видимости. NULL = границы нет."""
    nxt = getattr(c, "next_attempt_at", None)
    if nxt is None:
        return True
    return nxt <= (now or local_now())


def attempts_left(c) -> bool:
    return (getattr(c, "follow_up_count", 0) or 0) < NO_ANSWER_ESCALATE_AT


def no_contact(c) -> bool:
    """Три попытки исчерпаны — кандидат «не вышел на связь».

    Вычисляется, а не хранится: это тот же счётчик, посмотренный под другим
    углом. Отдельного этапа воронки не заводим — см. recruitment_stages.
    """
    return (getattr(c, "follow_up_count", 0) or 0) >= NO_ANSWER_ESCALATE_AT


def queue_stage_allowed(stage: str, quick_mode_enabled: bool) -> bool:
    """Подходит ли этап для очереди звонков.

    «новый» допустим только там, где опроса не будет вовсе: при включённом
    быстром режиме кандидат сначала должен пройти опрос, и звонить ему рано.
    """
    if stage in TERMINAL_STAGES:
        return False
    if stage == STAGE_ANSWERED:
        return True
    if stage == STAGE_NEW:
        return not quick_mode_enabled
    return False


def is_callable(c, stage: str, now: datetime | None, call_hours,
                quick_mode_enabled: bool = True) -> bool:
    """Нужен ли этому кандидату исходящий звонок прямо сейчас."""
    now = now or local_now()
    return all([
        bool(getattr(c, "phone", "")),
        stage not in TERMINAL_STAGES,
        queue_stage_allowed(stage, quick_mode_enabled),
        not bool(getattr(c, "is_paused", False)),
        attempts_left(c),
        # АБСОЛЮТНОЕ ВЕТО. Стоит раньше due() не случайно: это не одно из
        # условий доступности, а запрет, перекрывающий назначенное время.
        not called_today(c, now),
        # Второе вето, про другое: разговор сегодня уже состоялся. Без него
        # «Дозвонился» возвращал кандидата в очередь сразу же — счётчик
        # обнулён, назначенного времени нет, значит «ни разу не звонили».
        not handled_today(c, now),
        due(c, now),
        call_hours.is_within(now),
        # Кандидат написал и ждёт ответа, а времени звонка не назвал —
        # сначала отвечаем текстом, а не звоним вслепую.
        not (unhandled_inbound(c) and getattr(c, "next_attempt_at", None) is None),
    ])


# ── приоритет ────────────────────────────────────────────────────────────

def priority(c, now: datetime | None = None) -> tuple[int, str]:
    """(корзина, причина) — по какому основанию кандидат в очереди.

    Причина уезжает в интерфейс подписью «почему сейчас»: рекрутер должен
    видеть, обещали ли мы этот звонок или просто дошла очередь.
    """
    now = now or local_now()
    if getattr(c, "next_attempt_at", None) is not None:
        return PRIORITY_SCHEDULED, REASON_SCHEDULED
    if not (getattr(c, "follow_up_count", 0) or 0):
        return PRIORITY_NEVER_CALLED, REASON_NEVER_CALLED
    return PRIORITY_RETRY, REASON_RETRY


def sort_key(c, now: datetime | None = None):
    """Ключ сортировки очереди: сначала корзина, внутри — своё правило.

    P1 по возрастанию назначенного времени (самый просроченный первым),
    P2 по убыванию создания (свежий отклик горячее), P3 по возрастанию
    последней попытки (дольше всех ждёт). Разнонаправленные сортировки в
    одном ключе делаются знаком у timestamp — отсюда отрицания.
    """
    now = now or local_now()
    bucket, _ = priority(c, now)
    if bucket == PRIORITY_SCHEDULED:
        nxt = getattr(c, "next_attempt_at", None)
        return (bucket, nxt.timestamp() if nxt else 0.0)
    if bucket == PRIORITY_NEVER_CALLED:
        created = getattr(c, "created_at", None)
        return (bucket, -created.timestamp() if created else 0.0)
    last = getattr(c, "follow_up_last_sent_at", None)
    return (bucket, last.timestamp() if last else 0.0)
