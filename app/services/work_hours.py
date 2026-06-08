"""Shared "is automation allowed right now" check for AI interview & follow-up.

Both features used to depend on Telegram's own Business Hours setting
(configured directly on the connected personal account) to decide when to
talk to candidates — invisible from the admin panel and impossible to tune
without digging into Telegram's app settings. Making the rule explicit here
lets the admin adjust working days/hours from Settings, and lets the bot
explain itself to candidates instead of silently going quiet.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

DEFAULT_WORK_DAYS = [0, 1, 2, 3, 4]  # datetime.weekday(): Monday=0 .. Sunday=6
DEFAULT_HOURS_FROM = "10:00"
DEFAULT_HOURS_TO = "20:00"

_DAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _parse_hhmm(value, fallback: str) -> time:
    raw = str(value or "").strip() or fallback
    try:
        h, m = raw.split(":")
        return time(int(h), int(m))
    except Exception:
        h, m = fallback.split(":")
        return time(int(h), int(m))


def _work_days(cfg: dict) -> list[int]:
    days = cfg.get("automation_work_days")
    if isinstance(days, list) and days:
        try:
            parsed = sorted({int(d) for d in days if 0 <= int(d) <= 6})
            if parsed:
                return parsed
        except Exception:
            pass
    return DEFAULT_WORK_DAYS


def is_working_now(cfg: dict) -> bool:
    """True if the current Moscow time falls within configured automation working hours."""
    now = datetime.now(MOSCOW_TZ)
    if now.weekday() not in _work_days(cfg):
        return False
    hours_from = _parse_hhmm(cfg.get("automation_work_hours_from"), DEFAULT_HOURS_FROM)
    hours_to = _parse_hhmm(cfg.get("automation_work_hours_to"), DEFAULT_HOURS_TO)
    return hours_from <= now.time() < hours_to


def describe_hours(cfg: dict) -> str:
    """Human-readable summary, e.g. 'Пн–Пт, 10:00–20:00 (МСК)'."""
    days = _work_days(cfg)
    hours_from = (cfg.get("automation_work_hours_from") or DEFAULT_HOURS_FROM).strip() \
        if isinstance(cfg.get("automation_work_hours_from"), str) else DEFAULT_HOURS_FROM
    hours_to = (cfg.get("automation_work_hours_to") or DEFAULT_HOURS_TO).strip() \
        if isinstance(cfg.get("automation_work_hours_to"), str) else DEFAULT_HOURS_TO

    if len(days) > 1 and days == list(range(days[0], days[-1] + 1)):
        days_text = f"{_DAY_NAMES[days[0]]}–{_DAY_NAMES[days[-1]]}"
    else:
        days_text = ", ".join(_DAY_NAMES[d] for d in days)
    return f"{days_text}, {hours_from}–{hours_to} (МСК)"
