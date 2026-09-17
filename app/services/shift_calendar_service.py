"""Смены сотрудника в файле календаря (.ics) — «добавить в календарь телефона».

Зачем файл, а не ссылка на подписку: график живёт в Excel у руководителя и
меняется руками, подписка на календарь потребовала бы постоянно доступного
адреса и отдельной авторизации. Файл на месяц человек открывает один раз, и
смены со своими часами и напоминанием ложатся в календарь телефона.

Ссылку на файл открывает уже внешний браузер (во WebView скачивания нет),
поэтому обычная сессия туда не доедет. Отсюда одноразовая подписанная метка в
адресе: она живёт минуты, годится только для этого файла и не даёт ничего
больше.
"""
from __future__ import annotations

import base64
import calendar as _calendar
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

TOKEN_TTL_SECONDS = 15 * 60
# Напоминание за час: смена начинается в 10:00, а доехать надо заранее.
ALARM_BEFORE_MINUTES = 60
DEFAULT_HOURS = "10:00-22:00"
MONTHS_RU = ["январь", "февраль", "март", "апрель", "май", "июнь",
             "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


class BadToken(ValueError):
    """Метка в адресе просрочена или подделана."""


def _secret() -> bytes:
    from app.settings import settings

    return str(settings.secret_key).encode("utf-8")


def _sign(payload: bytes) -> str:
    digest = hmac.new(_secret(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest)[:27].decode("ascii")


def make_token(user_id: str, ttl: int = TOKEN_TTL_SECONDS) -> str:
    payload = json.dumps({"u": str(user_id), "e": int(time.time()) + ttl}, separators=(",", ":")).encode("utf-8")
    body = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"{body}.{_sign(payload)}"


def read_token(token: str) -> str:
    """Возвращает id пользователя или бросает BadToken."""
    try:
        body, signature = str(token).split(".", 1)
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    except Exception as exc:
        raise BadToken("malformed") from exc
    if not hmac.compare_digest(signature, _sign(payload)):
        raise BadToken("bad_signature")
    data = json.loads(payload.decode("utf-8"))
    if int(data.get("e", 0)) < int(time.time()):
        raise BadToken("expired")
    return str(data["u"])


@dataclass
class Shift:
    day: date
    point_name: str
    start: str      # «10:00»
    end: str        # «22:00»


def _hours_for(point_name: str, day: date) -> tuple[str, str]:
    """Часы работы точки из её карточки; выходные бывают другими."""
    from app.data.salon_repository import get_salon_repository

    hours = ""
    for salon in get_salon_repository().list_salons():
        if (salon.name or "").strip() == point_name:
            hours = (salon.work_hours_weekend if day.weekday() >= 5 else salon.work_hours_weekday) or ""
            break
    hours = (hours or DEFAULT_HOURS).replace(" ", "")
    start, _, end = hours.partition("-")
    return (start or "10:00"), (end or "22:00")


async def shifts_for(employee_name: str, year: int, month: int) -> list[Shift]:
    """Смены сотрудника за месяц из того же графика, что видит кабинет."""
    from app.services.schedule_service import ScheduleService

    data = await ScheduleService().get_schedule_month(year, month)
    points: dict[str, str] = data.get("points") or {}
    out: list[Shift] = []
    for row in data.get("days") or []:
        code = (row.get("assignments") or {}).get(employee_name)
        if not code:
            continue
        point_name = points.get(str(code).strip(), str(code).strip())
        day = date.fromisoformat(row["date"])
        start, end = _hours_for(point_name, day)
        out.append(Shift(day=day, point_name=point_name, start=start, end=end))
    return out


def _dt(day: date, hhmm: str) -> str:
    hour, _, minute = hhmm.partition(":")
    return f"{day.strftime('%Y%m%d')}T{int(hour or 0):02d}{int(minute or 0):02d}00"


def _escape(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")


def build_ics(shifts: list[Shift], employee_name: str, year: int, month: int) -> str:
    """Файл календаря: событие на смену с напоминанием за час.

    Время плавающее (без часового пояса) — телефон покажет его как местное, а
    другого часового пояса у салонов и нет. UID собирается из даты и
    сотрудника, поэтому повторная загрузка того же месяца не плодит дубликаты,
    а обновляет события.
    """
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    month_ru = MONTHS_RU[month - 1] if 1 <= month <= 12 else str(month)
    slug = hashlib.sha1(employee_name.encode("utf-8")).hexdigest()[:10]
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//BONJOUR//Смены//RU",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:Смены BONJOUR — {month_ru} {year}",
    ]
    for shift in shifts:
        lines += [
            "BEGIN:VEVENT",
            f"UID:bonjour-shift-{slug}-{shift.day.isoformat()}@bonjour.pw",
            f"DTSTAMP:{stamp}Z".replace("ZZ", "Z"),
            f"DTSTART:{_dt(shift.day, shift.start)}",
            f"DTEND:{_dt(shift.day, shift.end)}",
            f"SUMMARY:Смена · {_escape(shift.point_name)}",
            f"LOCATION:{_escape(shift.point_name)}",
            "DESCRIPTION:" + _escape(f"Смена {shift.start}–{shift.end}. График BONJOUR."),
            "BEGIN:VALARM",
            f"TRIGGER:-PT{ALARM_BEFORE_MINUTES}M",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_escape('Смена ' + shift.point_name + ' в ' + shift.start)}",
            "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    # В .ics строки разделяются CRLF — Android этого требует.
    return "\r\n".join(lines) + "\r\n"


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last = _calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def next_shift(shifts: list[Shift], now: Optional[datetime] = None) -> Optional[dict[str, Any]]:
    """Ближайшая смена — для подписи на кнопке в кабинете."""
    now = now or datetime.now()
    for shift in sorted(shifts, key=lambda s: s.day):
        start = datetime.combine(shift.day, datetime.min.time()) + timedelta(
            hours=int(shift.start.split(":")[0] or 0), minutes=int(shift.start.split(":")[1] or 0)
        )
        if start >= now - timedelta(hours=12):
            return {"date": shift.day.isoformat(), "point": shift.point_name,
                    "start": shift.start, "end": shift.end}
    return None
