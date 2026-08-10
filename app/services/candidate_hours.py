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
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

log = logging.getLogger(__name__)

CFG_ENABLED = "candidate_hours_enabled"
CFG_DAYS = "candidate_hours_days"      # список 1..7, где 1 = понедельник
CFG_START = "candidate_hours_start"    # "09:00"
CFG_END = "candidate_hours_end"        # "20:00"

DEFAULT_DAYS = [1, 2, 3, 4, 5]
DEFAULT_START = "09:00"
DEFAULT_END = "20:00"


def _parse_time(raw: str | None, fallback: str) -> time:
    for value in (raw, fallback):
        text = str(value or "").strip()
        if not text:
            continue
        try:
            hh, mm = text.split(":")[:2]
            return time(int(hh), int(mm))
        except Exception:
            continue
    return time(0, 0)


def load_schedule(cfg: dict | None = None) -> dict:
    """{enabled, days, start, end} — нормализованное расписание."""
    if cfg is None:
        from app.services.config_service import ConfigService
        cfg = ConfigService().load()

    raw_days = cfg.get(CFG_DAYS)
    if isinstance(raw_days, str):
        raw_days = [d for d in raw_days.replace(" ", "").split(",") if d]
    days: list[int] = []
    for d in (raw_days if isinstance(raw_days, (list, tuple)) else []):
        try:
            n = int(d)
        except Exception:
            continue
        if 1 <= n <= 7:
            days.append(n)
    days = sorted(set(days)) or list(DEFAULT_DAYS)

    return {
        "enabled": bool(cfg.get(CFG_ENABLED)),
        "days": days,
        "start": str(cfg.get(CFG_START) or DEFAULT_START),
        "end": str(cfg.get(CFG_END) or DEFAULT_END),
    }


def is_within(now: datetime | None = None, cfg: dict | None = None) -> bool:
    """Можно ли писать кандидату прямо сейчас."""
    schedule = load_schedule(cfg)
    if not schedule["enabled"]:
        return True  # расписание не настроено — прежнее поведение

    now = now or datetime.now()
    if now.isoweekday() not in schedule["days"]:
        return False

    start = _parse_time(schedule["start"], DEFAULT_START)
    end = _parse_time(schedule["end"], DEFAULT_END)
    current = now.time()
    if start <= end:
        return start <= current <= end
    # Окно через полночь (например 20:00–02:00): день начала считается рабочим.
    return current >= start or current <= end


def next_window_start(now: datetime | None = None, cfg: dict | None = None) -> datetime | None:
    """Когда откроется ближайшее рабочее окно. None — если оно уже открыто
    или расписание выключено. Нужен только для показа оператору."""
    schedule = load_schedule(cfg)
    if not schedule["enabled"]:
        return None
    now = now or datetime.now()
    if is_within(now, cfg):
        return None

    start = _parse_time(schedule["start"], DEFAULT_START)
    # Ищем ближайший подходящий день в пределах недели — дальше искать нечего,
    # список дней недельный по определению.
    for offset in range(0, 8):
        day = now + timedelta(days=offset)
        if day.isoweekday() not in schedule["days"]:
            continue
        candidate = day.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
        if candidate > now:
            return candidate
    return None
