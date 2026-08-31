"""Расписание общения с кандидатами: в какие дни и часы боту можно писать.

Зафиксированная логика (ровно то, ради чего это делалось):

* Кандидат ответил в нерабочее время — бот **молчит**, но ответ не теряется:
  он сохраняется в состояние опроса как отложенный. Когда наступают рабочие
  часы, цепочка **продолжается с того места, где остановилась**, а не
  начинается заново.
* Отложенное живёт в БД (quick_state_json кандидата), а не в памяти, поэтому
  переживает падение и перезапуск сервера: после восстановления фоновая
  задача просто находит отложенное и доигрывает его.
* Новый отклик, пришедший в нерабочее время, не получает приветствие сразу —
  опрос ставится в очередь (status="queued") и стартует в начале ближайшего
  рабочего окна.

Время считается по ЛОКАЛЬНОМУ времени сервера (UTC+3), а не по UTC: оператор
задаёт часы в том виде, в каком видит их на часах. Хранение — config.json,
как и остальные настройки.

Выключено по умолчанию: пока оператор не задал расписание, поведение ровно
прежнее — писать в любое время.

Механизм расчёта окна вынесен в app/services/work_hours.py: когда понадобилось
второе такое окно (для звонков, app/services/call_hours.py), копировать логику
дней и часов было нельзя. Здесь остался только НАБОР НАСТРОЕК — имена ключей и
значения по умолчанию, — а сам расчёт один на оба расписания.
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.services.hours_window import Schedule

log = logging.getLogger(__name__)

CFG_ENABLED = "candidate_hours_enabled"
CFG_DAYS = "candidate_hours_days"      # список 1..7, где 1 = понедельник
CFG_START = "candidate_hours_start"    # "09:00"
CFG_END = "candidate_hours_end"        # "20:00"

DEFAULT_DAYS = [1, 2, 3, 4, 5]
DEFAULT_START = "09:00"
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
    """{enabled, days, start, end} — нормализованное расписание."""
    return SCHEDULE.load(cfg)


def is_within(now: datetime | None = None, cfg: dict | None = None) -> bool:
    """Можно ли писать кандидату прямо сейчас."""
    return SCHEDULE.is_within(now, cfg)


def next_window_start(now: datetime | None = None, cfg: dict | None = None) -> datetime | None:
    """Когда откроется ближайшее рабочее окно. None — если оно уже открыто
    или расписание выключено. Нужен только для показа оператору."""
    return SCHEDULE.next_window_start(now, cfg)
