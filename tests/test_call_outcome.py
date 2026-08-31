"""Результаты звонков: счётчики, расписание следующей попытки, журнал, откат.

База настоящая (SQLite в tmp_path), потому что record_outcome коммитит сессию,
а именно порядок «изменили поля → записали журнал → commit» и проверяется.
Расписание звонков подменяется тестовым двойником: настоящее читает config.json
из корня репозитория, и тест не должен зависеть от боевых настроек.
"""
from datetime import datetime, timedelta

import pytest

from app.services import candidate_outreach as outreach
from app.services import call_queue
from app.services.hours_window import LOCAL_UTC_OFFSET
from app.services.recruitment_stages import (
    NO_ANSWER_ESCALATE_AT,
    STAGE_ANSWERED,
    STAGE_REJECTED,
)

MONDAY_NOON = datetime(2026, 8, 31, 12, 0)  # локальное время


def to_utc(local_dt):
    return local_dt - LOCAL_UTC_OFFSET


class Hours:
    """Окно звонков 10:00–20:00 по будням, без чтения config.json."""

    def __init__(self, enabled=True, start=10, end=20, days=(1, 2, 3, 4, 5)):
        self.enabled = enabled
        self.start = start
        self.end = end
        self.days = set(days)

    def is_within(self, now=None):
        if not self.enabled:
            return True
        return now.isoweekday() in self.days and self.start <= now.hour < self.end

    def window_start_on_or_after(self, moment):
        if not self.enabled:
            return moment if isinstance(moment, datetime) else datetime.combine(
                moment, datetime.min.time())
        if isinstance(moment, datetime):
            floor, day = moment, moment.date()
        else:
            floor, day = datetime.combine(moment, datetime.min.time()), moment
        for offset in range(8):
            d = day + timedelta(days=offset)
            if d.isoweekday() not in self.days:
                continue
            candidate = datetime.combine(d, datetime.min.time()).replace(hour=self.start)
            if candidate >= floor:
                return candidate
        return None

    def shift_into_window(self, moment):
        if not self.enabled or self.is_within(moment):
            return moment
        return self.window_start_on_or_after(moment) or moment


@pytest.fixture
def db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models.recruitment import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def candidate(db):
    from app.models.recruitment import Candidate, Vacancy

    v = Vacancy(title="Мастер", is_open=True, quick_mode_enabled=True)
    db.add(v)
    db.commit()
    c = Candidate(vacancy_id=v.id, name="Иван", phone="+79990000000",
                  source="avito", stage=STAGE_ANSWERED)
    db.add(c)
    db.commit()
    return c


def outcome(db, c, kind, **kw):
    kw.setdefault("call_hours", Hours())
    kw.setdefault("now", MONDAY_NOON)
    return outreach.record_outcome(db, c, kind, **kw)


# ── недозвон ─────────────────────────────────────────────────────────────

def test_no_answer_increments_and_schedules_next_day(db, candidate):
    res = outcome(db, candidate, outreach.OUTCOME_NO_ANSWER)

    assert res["call_attempts"] == 1
    # Следующая попытка — начало окна СЛЕДУЮЩЕГО дня, а не «через сутки».
    assert candidate.next_attempt_at == datetime(2026, 9, 1, 10, 0)
    assert candidate.follow_up_last_sent_at is not None


def test_no_answer_veto_holds_for_the_rest_of_the_day(db, candidate):
    outcome(db, candidate, outreach.OUTCOME_NO_ANSWER)

    # Тот же день, окно открыто, назначенное время ещё не наступило —
    # кандидата в очереди быть не должно ни по одному основанию.
    assert call_queue.called_today(candidate, MONDAY_NOON) is True
    assert call_queue.is_callable(
        candidate, STAGE_ANSWERED, MONDAY_NOON.replace(hour=18), Hours()) is False


def test_third_no_answer_stops_scheduling(db, candidate):
    for _ in range(NO_ANSWER_ESCALATE_AT):
        outcome(db, candidate, outreach.OUTCOME_NO_ANSWER)

    assert candidate.follow_up_count == NO_ANSWER_ESCALATE_AT
    assert call_queue.no_contact(candidate) is True
    # Звонить больше не будем — назначать время незачем.
    assert candidate.next_attempt_at is None


def test_no_answer_on_friday_evening_lands_on_monday(db, candidate):
    friday = datetime(2026, 9, 4, 19, 0)
    outcome(db, candidate, outreach.OUTCOME_NO_ANSWER, now=friday)

    assert candidate.next_attempt_at == datetime(2026, 9, 7, 10, 0)


# ── дозвонились ──────────────────────────────────────────────────────────

def test_reached_resets_counter_but_keeps_daily_veto(db, candidate):
    outcome(db, candidate, outreach.OUTCOME_NO_ANSWER)
    outcome(db, candidate, outreach.OUTCOME_REACHED)

    assert candidate.follow_up_count == 0
    assert candidate.next_attempt_at is None
    # Ключевое отличие от старой reset_call_attempts: отметку о звонке не
    # стираем, иначе кандидат тут же вернулся бы в очередь как «ни разу
    # не звонили».
    assert candidate.follow_up_last_sent_at is not None
    assert call_queue.called_today(candidate, MONDAY_NOON) is True


def test_reached_keeps_history(db, candidate):
    outcome(db, candidate, outreach.OUTCOME_NO_ANSWER)
    outcome(db, candidate, outreach.OUTCOME_REACHED)

    kinds = [e["outcome"] for e in candidate.call_log()]
    assert kinds == [outreach.OUTCOME_NO_ANSWER, outreach.OUTCOME_REACHED]


# ── перезвонить позже ────────────────────────────────────────────────────

def test_later_named_today_after_no_answer_moves_to_next_day(db, candidate):
    """Кандидат назвал «сегодня в 18:00», но сегодня мы уже звонили.

    Вето сильнее названного времени: второй автоматический звонок в тот же
    календарный день невозможен.
    """
    outcome(db, candidate, outreach.OUTCOME_NO_ANSWER)
    outcome(db, candidate, outreach.OUTCOME_LATER,
            next_at=MONDAY_NOON.replace(hour=18))

    assert candidate.next_attempt_at == datetime(2026, 9, 1, 10, 0)


def test_later_named_today_without_call_today_stays_today(db, candidate):
    outcome(db, candidate, outreach.OUTCOME_LATER,
            next_at=MONDAY_NOON.replace(hour=18))

    assert candidate.next_attempt_at == MONDAY_NOON.replace(hour=18)


def test_later_outside_window_shifts_into_window(db, candidate):
    outcome(db, candidate, outreach.OUTCOME_LATER,
            next_at=MONDAY_NOON.replace(hour=22))

    assert candidate.next_attempt_at == datetime(2026, 9, 1, 10, 0)


def test_later_is_not_an_outbound_attempt(db, candidate):
    outcome(db, candidate, outreach.OUTCOME_LATER,
            next_at=MONDAY_NOON.replace(hour=18))

    assert candidate.follow_up_count == 0
    assert candidate.follow_up_last_sent_at is None


def test_later_without_time_is_rejected(db, candidate):
    with pytest.raises(ValueError):
        outcome(db, candidate, outreach.OUTCOME_LATER)


# ── входящий контакт ─────────────────────────────────────────────────────

def test_inbound_does_not_consume_the_daily_attempt(db, candidate):
    outcome(db, candidate, outreach.OUTCOME_INBOUND)

    assert candidate.follow_up_count == 0
    assert candidate.follow_up_last_sent_at is None
    assert call_queue.called_today(candidate, MONDAY_NOON) is False


def test_any_outcome_clears_awaiting_reply(db, candidate):
    """Звонок идёт мимо переписки, поэтому «ждёт ответа» снимает результат."""
    candidate.last_message_from = "applicant"
    candidate.last_message_at = to_utc(MONDAY_NOON) - timedelta(hours=2)
    db.commit()
    assert call_queue.unhandled_inbound(candidate) is True

    outcome(db, candidate, outreach.OUTCOME_NO_ANSWER)

    assert call_queue.unhandled_inbound(candidate) is False


# ── отказ ────────────────────────────────────────────────────────────────

def test_rejected_moves_stage_and_clears_schedule(db, candidate):
    candidate.next_attempt_at = datetime(2026, 9, 1, 10, 0)
    db.commit()

    outcome(db, candidate, outreach.OUTCOME_REJECTED)

    assert candidate.stage == STAGE_REJECTED
    assert candidate.next_attempt_at is None


def test_unknown_outcome_is_rejected(db, candidate):
    with pytest.raises(ValueError):
        outcome(db, candidate, "maybe")


# ── журнал и откат ───────────────────────────────────────────────────────

def test_log_entry_records_outcome_and_time(db, candidate):
    outcome(db, candidate, outreach.OUTCOME_NO_ANSWER)

    log = candidate.call_log()
    assert len(log) == 1
    assert log[0]["outcome"] == outreach.OUTCOME_NO_ANSWER
    assert log[0]["message_sent"] is False
    assert log[0]["at"]


def test_broken_log_json_does_not_break_the_card(db, candidate):
    candidate.call_log_json = "{не json"
    db.commit()

    assert candidate.call_log() == []
    # И следующий результат просто начинает журнал заново, а не падает.
    outcome(db, candidate, outreach.OUTCOME_NO_ANSWER)
    assert len(candidate.call_log()) == 1


def test_undo_restores_previous_state(db, candidate):
    outcome(db, candidate, outreach.OUTCOME_NO_ANSWER)
    res = outreach.undo_last_outcome(db, candidate)

    assert res["undone"] == outreach.OUTCOME_NO_ANSWER
    assert candidate.follow_up_count == 0
    assert candidate.follow_up_last_sent_at is None
    assert candidate.next_attempt_at is None
    assert candidate.call_log() == []


def test_undo_reports_that_a_sent_message_stays_sent(db, candidate):
    outcome(db, candidate, outreach.OUTCOME_NO_ANSWER, message_sent=True)
    res = outreach.undo_last_outcome(db, candidate)

    assert res["message_not_recalled"] is True


def test_undo_restores_stage_after_rejection(db, candidate):
    outcome(db, candidate, outreach.OUTCOME_REJECTED)
    outreach.undo_last_outcome(db, candidate)

    assert candidate.stage == STAGE_ANSWERED


def test_undo_of_second_outcome_leaves_the_first(db, candidate):
    outcome(db, candidate, outreach.OUTCOME_NO_ANSWER)
    outcome(db, candidate, outreach.OUTCOME_REACHED)

    outreach.undo_last_outcome(db, candidate)

    assert candidate.follow_up_count == 1
    assert [e["outcome"] for e in candidate.call_log()] == [outreach.OUTCOME_NO_ANSWER]


def test_undo_with_empty_log_raises(db, candidate):
    with pytest.raises(ValueError):
        outreach.undo_last_outcome(db, candidate)


# ── флаги ────────────────────────────────────────────────────────────────

def test_flags_switch_to_no_contact_after_three_attempts(db, candidate):
    from app.services import recruitment_stages as rs

    for _ in range(NO_ANSWER_ESCALATE_AT):
        outcome(db, candidate, outreach.OUTCOME_NO_ANSWER)

    flags = rs.flags({}, call_attempts=candidate.follow_up_count)
    codes = [f["code"] for f in flags]
    assert rs.FLAG_NO_CONTACT in codes
    assert rs.FLAG_NO_ANSWER not in codes
    assert flags[0]["escalate"] is True


def test_awaiting_reply_flag_is_separate_from_no_answer():
    from app.services import recruitment_stages as rs

    codes = [f["code"] for f in rs.flags({}, call_attempts=1, awaiting_reply=True)]
    assert codes == [rs.FLAG_AWAITING_REPLY, rs.FLAG_NO_ANSWER]
