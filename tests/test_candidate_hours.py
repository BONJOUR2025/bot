"""Расписание общения с кандидатами: когда боту можно писать.

Зафиксированное поведение (оно же — постановка задачи):
кандидат ответил в нерабочее время → бот молчит, ответ не теряется, а
цепочка продолжается с места остановки, как только наступают рабочие часы,
и переживает перезапуск сервера.
"""
from __future__ import annotations

from datetime import datetime

from app.services import candidate_hours as ch


def _cfg(enabled=True, days=(1, 2, 3, 4, 5), start="09:00", end="20:00"):
    return {
        ch.CFG_ENABLED: enabled,
        ch.CFG_DAYS: list(days),
        ch.CFG_START: start,
        ch.CFG_END: end,
    }


# 2026-08-10 — понедельник, 2026-08-15 — суббота.
MON = datetime(2026, 8, 10)
SAT = datetime(2026, 8, 15)


class TestDisabledByDefault:
    def test_no_schedule_means_always_allowed(self):
        """Пока оператор не настроил расписание, поведение прежнее — иначе
        включение фичи молча заткнуло бы бота."""
        assert ch.is_within(MON.replace(hour=3), cfg={}) is True
        assert ch.is_within(SAT.replace(hour=23), cfg={}) is True

    def test_explicitly_disabled_is_allowed(self):
        assert ch.is_within(MON.replace(hour=3), cfg=_cfg(enabled=False)) is True


class TestWorkingWindow:
    def test_inside_the_window(self):
        assert ch.is_within(MON.replace(hour=9, minute=0), cfg=_cfg()) is True
        assert ch.is_within(MON.replace(hour=14), cfg=_cfg()) is True
        assert ch.is_within(MON.replace(hour=20, minute=0), cfg=_cfg()) is True

    def test_before_and_after(self):
        assert ch.is_within(MON.replace(hour=8, minute=59), cfg=_cfg()) is False
        assert ch.is_within(MON.replace(hour=20, minute=1), cfg=_cfg()) is False
        assert ch.is_within(MON.replace(hour=3), cfg=_cfg()) is False

    def test_non_working_day(self):
        assert ch.is_within(SAT.replace(hour=14), cfg=_cfg()) is False

    def test_weekend_can_be_enabled(self):
        assert ch.is_within(SAT.replace(hour=14), cfg=_cfg(days=(1, 2, 3, 4, 5, 6, 7))) is True


class TestOvernightWindow:
    """Окно 20:00–02:00 переворачивает сравнение — частый источник ошибок."""

    def test_late_evening_is_inside(self):
        assert ch.is_within(MON.replace(hour=23), cfg=_cfg(start="20:00", end="02:00")) is True

    def test_after_midnight_is_inside(self):
        assert ch.is_within(MON.replace(hour=1), cfg=_cfg(start="20:00", end="02:00")) is True

    def test_daytime_is_outside(self):
        assert ch.is_within(MON.replace(hour=12), cfg=_cfg(start="20:00", end="02:00")) is False


class TestNextWindowStart:
    def test_none_when_already_open(self):
        assert ch.next_window_start(MON.replace(hour=10), cfg=_cfg()) is None

    def test_none_when_schedule_disabled(self):
        assert ch.next_window_start(MON.replace(hour=3), cfg=_cfg(enabled=False)) is None

    def test_same_day_morning(self):
        nxt = ch.next_window_start(MON.replace(hour=6), cfg=_cfg())
        assert nxt == MON.replace(hour=9, minute=0, second=0, microsecond=0)

    def test_skips_the_weekend(self):
        """Вечер пятницы → ближайшее окно в понедельник, а не в субботу."""
        friday = datetime(2026, 8, 14, 22)
        nxt = ch.next_window_start(friday, cfg=_cfg())
        assert nxt is not None
        assert nxt.isoweekday() == 1
        assert (nxt.hour, nxt.minute) == (9, 0)


class TestMalformedConfig:
    def test_broken_time_falls_back_instead_of_raising(self):
        """Кривое значение в конфиге не должно ронять обработку сообщений —
        цена ошибки здесь: бот молчит либо пишет не в те часы, но живой."""
        assert ch.is_within(MON.replace(hour=12), cfg=_cfg(start="дичь", end="20:00")) in (True, False)

    def test_days_accept_a_comma_string(self):
        """Значение могло прийти из формы строкой."""
        cfg = _cfg()
        cfg[ch.CFG_DAYS] = "1,2,3"
        assert ch.load_schedule(cfg)["days"] == [1, 2, 3]

    def test_empty_days_falls_back_to_workweek(self):
        cfg = _cfg(days=())
        assert ch.load_schedule(cfg)["days"] == [1, 2, 3, 4, 5]
