"""Окно звонков: когда рекрутеру можно предлагать исходящий звонок.

Отдельное от candidate_hours намеренно. То окно сдерживает автоматическую
переписку бота, это — ручные звонки человека, и совпадать они не обязаны:
писать в чат можно с девяти, а звонить в девять уже неловко. Механизм расчёта
при этом общий (app/services/work_hours.py) — здесь только набор ключей и
значения по умолчанию.

Выключенное окно разрешает звонить в любое время: пока оператор его не задал,
режим «Прозвон» не должен молчать.
"""
from __future__ import annotations

from datetime import date, datetime

from app.services.hours_window import Schedule, local_now, to_local

CFG_ENABLED = "call_hours_enabled"
CFG_DAYS = "call_hours_days"      # список 1..7, где 1 = понедельник
CFG_START = "call_hours_start"    # "10:00"
CFG_END = "call_hours_end"        # "20:00"

DEFAULT_DAYS = [1, 2, 3, 4, 5]
DEFAULT_START = "10:00"
DEFAULT_END = "20:00"

SCHEDULE = Schedule(
    key_enabled=CFG_ENABLED,
    key_days=CFG_DAYS,
    key_start=CFG_START,
    key_end=CFG_END,
    default_days=tuple(DEFAULT_DAYS),
    default_start=DEFAULT_START,
    default_end=DEFAULT_END,
)


def load_schedule(cfg: dict | None = None) -> dict:
    return SCHEDULE.load(cfg)


def is_within(now: datetime | None = None, cfg: dict | None = None) -> bool:
    """Можно ли звонить прямо сейчас."""
    return SCHEDULE.is_within(now, cfg)


def next_window_start(now: datetime | None = None, cfg: dict | None = None) -> datetime | None:
    """Когда откроется ближайшее окно звонков. None — если уже открыто."""
    return SCHEDULE.next_window_start(now, cfg)


def window_start_on_or_after(
    moment: datetime | date, cfg: dict | None = None
) -> datetime | None:
    return SCHEDULE.window_start_on_or_after(moment, cfg)


def shift_into_window(moment: datetime, cfg: dict | None = None) -> datetime:
    return SCHEDULE.shift_into_window(moment, cfg)


__all__ = [
    "SCHEDULE", "CFG_ENABLED", "CFG_DAYS", "CFG_START", "CFG_END",
    "DEFAULT_DAYS", "DEFAULT_START", "DEFAULT_END",
    "load_schedule", "is_within", "next_window_start",
    "window_start_on_or_after", "shift_into_window",
    "local_now", "to_local",
]
