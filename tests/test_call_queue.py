"""Очередь «Прозвон»: предикат, вето одной попытки в день, приоритеты.

Тесты на голых данных, без БД и без FastAPI — call_queue намеренно не знает
про SQLAlchemy, поэтому кандидата достаточно изобразить простым объектом.
Тот же приём, что в тестах recruitment_stages.

Всё время в тестах ЛОКАЛЬНОЕ, кроме полей кандидата: follow_up_last_sent_at и
last_message_at хранятся в UTC, как их пишет приложение. Именно на этом стыке
и живёт проверка границы календарного дня.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import call_hours as call_hours_module
from app.services import call_queue as cq
from app.services.recruitment_stages import (
    STAGE_ANSWERED, STAGE_HIRED, STAGE_NEW, STAGE_REJECTED, STAGE_THINKING,
)
from app.services.hours_window import LOCAL_UTC_OFFSET


class Hours:
    """Окно звонков с фиксированным конфигом.

    Ровно тот интерфейс, который нужен call_queue: is_within,
    window_start_on_or_after, shift_into_window. Больше он ни на что
    не опирается, поэтому подменяется тремя методами.
    """

    def __init__(self, **cfg):
        base = {
            "call_hours_enabled": True,
            "call_hours_days": [1, 2, 3, 4, 5],
            "call_hours_start": "10:00",
            "call_hours_end": "20:00",
        }
        base.update(cfg)
        self.cfg = base

    def is_within(self, now):
        return call_hours_module.SCHEDULE.is_within(now, self.cfg)

    def window_start_on_or_after(self, moment):
        return call_hours_module.SCHEDULE.window_start_on_or_after(moment, self.cfg)

    def shift_into_window(self, moment):
        return call_hours_module.SCHEDULE.shift_into_window(moment, self.cfg)


def to_utc(local_dt):
    """Локальное время → то, что лежало бы в БД."""
    return local_dt - LOCAL_UTC_OFFSET


def make_candidate(**kw):
    data = {
        "id": 1,
        "phone": "+79211234567",
        "is_paused": False,
        "follow_up_count": 0,
        "follow_up_last_sent_at": None,
        "next_attempt_at": None,
        "last_message_from": "",
        "last_message_at": None,
        "last_inbound_handled_at": None,
        "created_at": datetime(2026, 8, 25, 12, 0),
    }
    data.update(kw)
    return SimpleNamespace(**data)


# Понедельник 31.08.2026, 12:00 локального времени — внутри окна 10:00–20:00.
MONDAY_NOON = datetime(2026, 8, 31, 12, 0)


# ── 1. новый кандидат → P2 ───────────────────────────────────────────────

def test_new_candidate_is_callable_and_lands_in_p2():
    c = make_candidate()
    hours = Hours()
    assert cq.is_callable(c, STAGE_ANSWERED, MONDAY_NOON, hours)
    bucket, reason = cq.priority(c, MONDAY_NOON)
    assert bucket == cq.PRIORITY_NEVER_CALLED
    assert reason == cq.REASON_NEVER_CALLED


def test_candidate_without_phone_never_in_queue():
    c = make_candidate(phone="")
    assert not cq.is_callable(c, STAGE_ANSWERED, MONDAY_NOON, Hours())


def test_paused_candidate_not_in_queue():
    c = make_candidate(is_paused=True)
    assert not cq.is_callable(c, STAGE_ANSWERED, MONDAY_NOON, Hours())


@pytest.mark.parametrize("stage", [STAGE_HIRED, STAGE_REJECTED, STAGE_THINKING])
def test_terminal_and_manual_stages_excluded(stage):
    """«нанят»/«отказ» терминальны, «думает» — ручной сценарий."""
    c = make_candidate()
    assert not cq.is_callable(c, stage, MONDAY_NOON, Hours())


def test_new_stage_allowed_only_without_quick_mode():
    """С включённым опросом кандидату на этапе «новый» звонить рано."""
    c = make_candidate()
    hours = Hours()
    assert not cq.is_callable(c, STAGE_NEW, MONDAY_NOON, hours, quick_mode_enabled=True)
    assert cq.is_callable(c, STAGE_NEW, MONDAY_NOON, hours, quick_mode_enabled=False)


# ── 3–4. недозвон №1 и запрет второго звонка в тот же день ───────────────

def test_no_answer_next_attempt_is_next_day():
    """Следующая попытка — начало окна следующего допустимого дня."""
    hours = Hours()
    nxt = cq.next_allowed_call_time(MONDAY_NOON, hours)
    assert nxt == datetime(2026, 9, 1, 10, 0)


def test_called_today_vetoes_queue():
    """Позвонили сегодня в 10:00 — в 12:00 кандидата в очереди нет."""
    c = make_candidate(
        follow_up_count=1,
        follow_up_last_sent_at=to_utc(datetime(2026, 8, 31, 10, 0)),
    )
    assert cq.called_today(c, MONDAY_NOON)
    assert not cq.is_callable(c, STAGE_ANSWERED, MONDAY_NOON, Hours())


def test_veto_beats_scheduled_time():
    """Вето сильнее назначенного времени: next_attempt_at наступил, но
    сегодня уже звонили — кандидата в очереди нет."""
    c = make_candidate(
        follow_up_count=1,
        follow_up_last_sent_at=to_utc(datetime(2026, 8, 31, 10, 0)),
        next_attempt_at=datetime(2026, 8, 31, 11, 0),
    )
    assert cq.due(c, MONDAY_NOON)          # время наступило
    assert not cq.is_callable(c, STAGE_ANSWERED, MONDAY_NOON, Hours())


# ── 5. следующий день → P3 ───────────────────────────────────────────────

def test_next_day_candidate_returns_as_retry():
    c = make_candidate(
        follow_up_count=1,
        follow_up_last_sent_at=to_utc(datetime(2026, 8, 31, 10, 0)),
    )
    tuesday = datetime(2026, 9, 1, 11, 0)
    assert not cq.called_today(c, tuesday)
    assert cq.is_callable(c, STAGE_ANSWERED, tuesday, Hours())
    bucket, reason = cq.priority(c, tuesday)
    assert bucket == cq.PRIORITY_RETRY
    assert reason == cq.REASON_RETRY


# ── 7. три попытки → no_contact ──────────────────────────────────────────

def test_three_attempts_exhausted():
    c = make_candidate(
        follow_up_count=3,
        follow_up_last_sent_at=to_utc(datetime(2026, 8, 28, 10, 0)),
    )
    assert cq.no_contact(c)
    assert not cq.attempts_left(c)
    assert not cq.is_callable(c, STAGE_ANSWERED, MONDAY_NOON, Hours())


def test_two_attempts_still_callable_next_day():
    c = make_candidate(
        follow_up_count=2,
        follow_up_last_sent_at=to_utc(datetime(2026, 8, 28, 10, 0)),
    )
    assert not cq.no_contact(c)
    assert cq.is_callable(c, STAGE_ANSWERED, MONDAY_NOON, Hours())


# ── 11, 15, 16. входящие ─────────────────────────────────────────────────

def test_inbound_without_time_keeps_candidate_out_of_queue():
    """Кандидат написал без конкретного времени — сначала отвечаем в чат."""
    c = make_candidate(
        last_message_from="applicant",
        last_message_at=to_utc(datetime(2026, 8, 31, 11, 0)),
    )
    assert cq.unhandled_inbound(c)
    assert not cq.is_callable(c, STAGE_ANSWERED, MONDAY_NOON, Hours())


def test_inbound_with_scheduled_time_stays_in_queue():
    """Если время назначено, входящее не выбрасывает из очереди."""
    c = make_candidate(
        last_message_from="applicant",
        last_message_at=to_utc(datetime(2026, 8, 31, 11, 0)),
        next_attempt_at=datetime(2026, 8, 31, 11, 30),
    )
    assert cq.unhandled_inbound(c)
    assert cq.is_callable(c, STAGE_ANSWERED, MONDAY_NOON, Hours())


def test_call_outcome_clears_old_inbound():
    """Старое входящее не держит кандидата вечно: результат звонка
    проставляет last_inbound_handled_at."""
    msg_at = to_utc(datetime(2026, 7, 1, 9, 0))
    c = make_candidate(last_message_from="applicant", last_message_at=msg_at)
    assert cq.unhandled_inbound(c)
    c.last_inbound_handled_at = msg_at + timedelta(minutes=5)
    assert not cq.unhandled_inbound(c)


def test_outgoing_message_clears_awaiting_reply():
    """Ответ в чат снимает признак сам — через last_message_from."""
    c = make_candidate(
        last_message_from="applicant",
        last_message_at=to_utc(datetime(2026, 8, 31, 11, 0)),
    )
    assert cq.unhandled_inbound(c)
    c.last_message_from = "employer"
    assert not cq.unhandled_inbound(c)


# ── 12–13. названное кандидатом время и вето ─────────────────────────────

def test_candidate_named_time_after_todays_attempt_moves_to_next_day():
    """Недозвон в 10:00, кандидат просит «после 18:00» — сегодня звонка нет."""
    c = make_candidate(
        follow_up_count=1,
        follow_up_last_sent_at=to_utc(datetime(2026, 8, 31, 10, 0)),
    )
    hours = Hours()
    wanted = datetime(2026, 8, 31, 18, 0)
    normalized = cq.normalize(wanted, c, hours, now=MONDAY_NOON)
    assert normalized == datetime(2026, 9, 1, 10, 0)

    c.next_attempt_at = normalized
    at_18 = datetime(2026, 8, 31, 18, 0)
    assert not cq.is_callable(c, STAGE_ANSWERED, at_18, hours)


def test_candidate_named_time_before_any_attempt_is_kept():
    """«Позвоните сегодня в 18:00», сегодня ещё не звонили — время остаётся."""
    c = make_candidate()
    hours = Hours()
    wanted = datetime(2026, 8, 31, 18, 0)
    normalized = cq.normalize(wanted, c, hours, now=MONDAY_NOON)
    assert normalized == wanted

    c.next_attempt_at = normalized
    assert not cq.is_callable(c, STAGE_ANSWERED, datetime(2026, 8, 31, 17, 0), hours)
    at_18 = datetime(2026, 8, 31, 18, 0)
    assert cq.is_callable(c, STAGE_ANSWERED, at_18, hours)
    assert cq.priority(c, at_18)[0] == cq.PRIORITY_SCHEDULED


# ── 17. нормализация в окно ──────────────────────────────────────────────

def test_time_outside_window_shifts_into_window():
    """«Позвоните в 23:00» → ближайшее допустимое утро."""
    c = make_candidate()
    hours = Hours()
    normalized = cq.normalize(datetime(2026, 8, 31, 23, 0), c, hours, now=MONDAY_NOON)
    assert normalized == datetime(2026, 9, 1, 10, 0)


def test_outside_call_hours_queue_is_empty():
    c = make_candidate()
    hours = Hours()
    assert not cq.is_callable(c, STAGE_ANSWERED, datetime(2026, 8, 31, 22, 0), hours)


def test_disabled_window_allows_any_time():
    """Окно выключено — звоним когда угодно, прежнее поведение."""
    c = make_candidate()
    hours = Hours(call_hours_enabled=False)
    assert cq.is_callable(c, STAGE_ANSWERED, datetime(2026, 8, 31, 3, 0), hours)


def test_weekend_excluded_when_window_enabled():
    c = make_candidate()
    saturday = datetime(2026, 8, 29, 12, 0)
    assert not cq.is_callable(c, STAGE_ANSWERED, saturday, Hours())


# ── 21. граница календарного дня в локальном времени ─────────────────────

def test_local_calendar_day_boundary():
    """Звонок в 01:00 по локальному времени — сегодняшняя попытка.

    В UTC этот момент относится к предыдущим суткам (22:00). Если бы
    сравнение шло по UTC, правило «одна попытка в день» каждую ночь
    разъезжалось бы на три часа и разрешало второй звонок.
    """
    local_call = datetime(2026, 8, 31, 1, 0)
    stored = to_utc(local_call)
    assert stored.date() != local_call.date()  # именно тот случай

    c = make_candidate(follow_up_count=1, follow_up_last_sent_at=stored)
    assert cq.called_today(c, datetime(2026, 8, 31, 12, 0))
    assert not cq.called_today(c, datetime(2026, 9, 1, 12, 0))


# ── сортировка очереди ───────────────────────────────────────────────────

def test_queue_order_scheduled_then_new_then_retry():
    overdue = make_candidate(id=1, next_attempt_at=datetime(2026, 8, 31, 9, 0))
    scheduled = make_candidate(id=2, next_attempt_at=datetime(2026, 8, 31, 11, 0))
    fresh = make_candidate(id=3, created_at=datetime(2026, 8, 30, 12, 0))
    older = make_candidate(id=4, created_at=datetime(2026, 8, 20, 12, 0))
    retry = make_candidate(
        id=5, follow_up_count=1,
        follow_up_last_sent_at=to_utc(datetime(2026, 8, 28, 10, 0)),
    )

    ordered = sorted([retry, older, fresh, scheduled, overdue],
                     key=lambda c: cq.sort_key(c, MONDAY_NOON))
    assert [c.id for c in ordered] == [1, 2, 3, 4, 5]
