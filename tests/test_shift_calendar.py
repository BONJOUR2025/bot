"""Смены в календарь телефона: файл .ics и подписанная ссылка на него.

Ссылку открывает внешний браузер, поэтому проверяется главное: метка живёт
недолго, подделать её нельзя, и по ней отдаются смены того, кому она выдана.
"""
from __future__ import annotations

import asyncio
import time
from datetime import date, datetime

import pytest

from app.services import shift_calendar_service as cal


def _shift(day, point="Гранд Палас", start="10:00", end="22:00"):
    return cal.Shift(day=date.fromisoformat(day), point_name=point, start=start, end=end)


# ── Метка в ссылке ────────────────────────────────────────────────

def test_token_round_trip():
    assert cal.read_token(cal.make_token("user-7")) == "user-7"


def test_expired_token_is_refused(monkeypatch):
    token = cal.make_token("user-7", ttl=1)
    monkeypatch.setattr(time, "time", lambda: time.__dict__ and 10 ** 10)
    with pytest.raises(cal.BadToken):
        cal.read_token(token)


def test_tampered_token_is_refused():
    token = cal.make_token("user-7")
    body, signature = token.split(".", 1)
    with pytest.raises(cal.BadToken):
        cal.read_token(f"{body}.{'a' * len(signature)}")
    with pytest.raises(cal.BadToken):
        cal.read_token("совсем не метка")


def test_token_of_one_user_does_not_open_anothers(monkeypatch):
    assert cal.read_token(cal.make_token("a")) != cal.read_token(cal.make_token("b"))


# ── Сам файл ──────────────────────────────────────────────────────

def test_ics_has_an_event_per_shift_with_alarm():
    ics = cal.build_ics([_shift("2026-09-18"), _shift("2026-09-20", "Пассаж", "11:00", "22:00")],
                        "Иванова А.", 2026, 9)
    assert ics.count("BEGIN:VEVENT") == 2 and ics.count("BEGIN:VALARM") == 2
    assert "DTSTART:20260918T100000" in ics and "DTEND:20260918T220000" in ics
    assert "DTSTART:20260920T110000" in ics
    assert "SUMMARY:Смена · Гранд Палас" in ics
    assert f"TRIGGER:-PT{cal.ALARM_BEFORE_MINUTES}M" in ics
    assert ics.endswith("END:VCALENDAR\r\n") and "\r\n" in ics


def test_same_month_loaded_twice_updates_events_instead_of_doubling():
    """UID собран из даты и сотрудника, поэтому календарь обновит, а не задвоит."""
    first = cal.build_ics([_shift("2026-09-18")], "Иванова А.", 2026, 9)
    second = cal.build_ics([_shift("2026-09-18", start="12:00")], "Иванова А.", 2026, 9)
    uid = [line for line in first.splitlines() if line.startswith("UID:")][0]
    assert uid in second


def test_empty_month_is_a_valid_but_empty_calendar():
    ics = cal.build_ics([], "Иванова А.", 2026, 9)
    assert "BEGIN:VEVENT" not in ics and ics.startswith("BEGIN:VCALENDAR")


def test_commas_in_the_point_name_do_not_break_the_file():
    """Запятая в .ics разделяет значения — её обязательно экранировать."""
    ics = cal.build_ics([_shift("2026-09-18", 'ТЦ "Академ Парк", 2 этаж')], "И", 2026, 9)
    assert 'SUMMARY:Смена · ТЦ "Академ Парк"\, 2 этаж' in ics


# ── Часы точки и ближайшая смена ──────────────────────────────────

class _Salon:
    def __init__(self, name, weekday="10:00-22:00", weekend="11:00-21:00"):
        self.name, self.work_hours_weekday, self.work_hours_weekend = name, weekday, weekend


def test_weekend_hours_come_from_the_salon_card(monkeypatch):
    class _Repo:
        def list_salons(self, status=None):
            return [_Salon("Гранд Палас")]

    monkeypatch.setattr("app.data.salon_repository.get_salon_repository", lambda: _Repo())
    assert cal._hours_for("Гранд Палас", date(2026, 9, 18)) == ("10:00", "22:00")   # пятница
    assert cal._hours_for("Гранд Палас", date(2026, 9, 19)) == ("11:00", "21:00")   # суббота
    assert cal._hours_for("Неизвестная", date(2026, 9, 18)) == ("10:00", "22:00")   # по умолчанию


def test_next_shift_is_the_first_upcoming_one():
    shifts = [_shift("2026-09-10"), _shift("2026-09-18"), _shift("2026-09-25")]
    nxt = cal.next_shift(shifts, now=datetime(2026, 9, 17, 15, 0))
    assert nxt["date"] == "2026-09-18" and nxt["start"] == "10:00"
    assert cal.next_shift([_shift("2026-09-01")], now=datetime(2026, 9, 17, 15, 0)) is None


def test_shifts_are_taken_from_the_same_schedule_the_cabinet_shows(monkeypatch):
    month = {
        "points": {"Гп": "Гранд Палас", "А": 'ТЦ "Академ Парк"'},
        "days": [
            {"date": "2026-09-18", "assignments": {"Вера 0102": "Гп", "Юлия 1010": "А"}},
            {"date": "2026-09-19", "assignments": {"Юлия 1010": "А"}},
            {"date": "2026-09-20", "assignments": {"Вера 0102": "А"}},
        ],
    }

    class _Service:
        async def get_schedule_month(self, year, month_no):
            return month

    monkeypatch.setattr("app.services.schedule_service.ScheduleService", _Service)
    monkeypatch.setattr(cal, "_hours_for", lambda point, day: ("10:00", "22:00"))
    shifts = asyncio.run(cal.shifts_for("Вера 0102", 2026, 9))
    assert [(s.day.isoformat(), s.point_name) for s in shifts] == [
        ("2026-09-18", "Гранд Палас"), ("2026-09-20", 'ТЦ "Академ Парк"')
    ]
