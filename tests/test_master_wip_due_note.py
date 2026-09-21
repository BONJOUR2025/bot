"""Строка заказа в боте «Что на мне висит» показывает срок выдачи, а не возраст."""
from datetime import date, timedelta

from app.handlers.user.master import _due_note


def _row(**kw):
    base = {"due": None, "due_state": None, "overdue_days": None, "days": 0}
    base.update(kw)
    return base


def test_future_due_shows_days_left_not_age():
    due = (date.today() + timedelta(days=10)).isoformat() + "T19:00"
    assert _due_note(_row(due=due, days=0)) == " · до выдачи 10 дн"


def test_overdue_today_tomorrow():
    assert _due_note(_row(due="2026-01-01T19:00", due_state="overdue", overdue_days=2)) == " · просрочен на 2 дн"
    assert _due_note(_row(due="2026-01-01T19:00", due_state="today")) == " · сдать сегодня до 19:00"
    assert _due_note(_row(due="2026-01-01T12:30", due_state="tomorrow")) == " · сдать завтра до 12:30"


def test_age_only_when_stale():
    assert _due_note(_row(days=3)) == ""
    assert _due_note(_row(days=12)) == " · в работе 12 дн"
