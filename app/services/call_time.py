"""Извлечение времени звонка из сообщения кандидата.

Зачем. Кандидаты постоянно назначают время сами: «Завтра в 14:00», «часа в
3 будет удобно», «после 17». Раньше это оседало обычным уведомлением, и
дальше всё держалось на памяти человека. Не удержалось: Бугай Егор написал
«Завтра в 14:00», никто не позвонил, и заметили это только через сутки, при
чтении переписок. Второй такой же случай — Федотов.

Что делает. Достаёт дату и время, приводит к абсолютным значениям
относительно «сейчас» и отдаёт вызывающему, который заводит задачу с
напоминанием.

Чего НЕ делает. Не отвечает кандидату и не подтверждает договорённость —
это обещание от имени человека, и решение о нём принимает человек.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, time, timedelta

log = logging.getLogger(__name__)

# Дешёвый предфильтр: без намёка на время модель не зовём вовсе. Ловит
# «в 14», «14:00», «в три», «завтра», «после обеда» — то есть всё, что в
# наших переписках реально встречалось.
_TIME_HINT = re.compile(
    r"\d{1,2}[:.]\d{2}|\d{1,2}\s*(часов|часа|час)\b|"
    # Предлог времени + число. Именно предлог отличает «после 17 смогу» от
    # «работаю 8 лет»: голое число в предфильтр не берём, иначе модель
    # начнёт искать время в рассказе про стаж — и, как показал замер,
    # находить его там, где его нет.
    r"\b(в|к|до|с|после|около|ближе\s+к)\s*\d{1,2}\b|"
    r"\b(сегодня|завтра|послезавтра|утром|днём|днем|вечером|после\s+обеда|"
    r"понедельник|вторник|сред[уы]|четверг|пятниц[уы]|суббот[уы]|воскресень)",
    re.IGNORECASE,
)

_WEEKDAYS = "понедельник вторник среда четверг пятница суббота воскресенье".split()

# Час назван явно: цифрой либо частью суток. Проверяется отдельно от
# _TIME_HINT, потому что тот срабатывает и на голое «завтра».
_HOUR_NAMED = re.compile(
    r"\d|\b(утром|утра|днём|днем|вечером|вечера|ночью|после\s+обеда|"
    r"в\s+обед|к\s+обеду)\b",
    re.IGNORECASE,
)


def looks_like_time(text: str) -> bool:
    return bool(_TIME_HINT.search(text or ""))


_DAY_WORDS = {
    "today": 0, "tomorrow": 1, "day_after": 2,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
_WEEKDAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _resolve_day(day_word, t: time, now: datetime) -> date | None:
    """Слово о дне → конкретная дата. Арифметика намеренно здесь, а не в модели.

    Замер показал, почему: на просьбу вернуть готовую дату модель выдала
    «2023-08-14» вместо 2026 года и назвала 18 августа понедельником, хотя
    это вторник. Слово «завтра» она при этом распознаёт безошибочно —
    вот его и спрашиваем, а календарь считаем сами.
    """
    word = (str(day_word) or "").strip().lower()

    if word in _WEEKDAY_NAMES:
        target = _WEEKDAY_NAMES.index(word)
        ahead = (target - now.weekday()) % 7
        # «В понедельник», сказанное в понедельник, означает следующий.
        return (now + timedelta(days=ahead or 7)).date()

    if word in ("today", "tomorrow", "day_after"):
        return (now + timedelta(days=_DAY_WORDS[word])).date()

    # День не назван — значит «сегодня», а если это время уже прошло, то завтра:
    # «после 17», написанное в 18:00, разумнее понять как завтрашние 17:00.
    if datetime.combine(now.date(), t) >= now - timedelta(minutes=5):
        return now.date()
    return (now + timedelta(days=1)).date()


def extract(text: str, cfg: dict, now: datetime | None = None) -> tuple[date, time] | None:
    """(дата, время) звонка или None.

    None означает «не уверены» — и это правильный ответ по умолчанию:
    выдуманное напоминание на несуществующую договорённость хуже, чем его
    отсутствие, потому что ему поверят.
    """
    text = (text or "").strip()
    if not text or not looks_like_time(text):
        return None
    # Час должен быть назван в самом сообщении — цифрой или частью суток.
    # Без этого модель его выдумывает: на «можем завтра созвониться», где
    # времени нет вовсе, она уверенно вернула 14:00. Напоминание на час,
    # который никто не назначал, хуже отсутствия напоминания.
    if not _HOUR_NAMED.search(text):
        return None

    from app.services.llm_client import chat, get_client

    if not get_client(cfg):
        return None  # без модели не угадываем

    now = now or datetime.now()
    try:
        raw = chat(
            cfg,
            [{"role": "user", "content": text}],
            system=(
                "Кандидат пишет, когда ему удобно созвониться. Верни, какой ДЕНЬ он "
                "назвал словом и какое время. Дату не вычисляй.\n"
                "day: today, tomorrow, day_after, monday, tuesday, wednesday, thursday, "
                "friday, saturday, sunday или null, если день не назван.\n"
                "time: ЧЧ:ММ. Неточное время округли: утро 10:00, день 14:00, "
                "после обеда 15:00, вечер 18:00. «после 17» — это 17:00.\n"
                "Если времени нет — null.\n"
                'Ответь ТОЛЬКО JSON: {"day": "...", "time": "ЧЧ:ММ или null"}'
            ),
            max_tokens=60,
            employee_id="quick_screening",
            employee_name="Быстрый режим (кандидаты)",
            feature="call_time",
        )
    except Exception as e:
        log.warning("call_time: LLM call failed: %s", e)
        return None

    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group())
    except Exception:
        return None

    t_raw = data.get("time")
    if not t_raw or str(t_raw).lower() == "null":
        return None
    try:
        t = datetime.strptime(str(t_raw), "%H:%M").time()
    except Exception:
        return None

    d = _resolve_day(data.get("day"), t, now)
    if d is None:
        return None

    # Дата в прошлом — почти наверняка модель ошиблась с «завтра»/«сегодня».
    # Молчим, а не переносим наугад: неверное напоминание хуже отсутствия.
    if datetime.combine(d, t) < now - timedelta(minutes=5):
        log.info("call_time: получена прошедшая дата %s %s, игнорируем", d, t)
        return None
    # Дальше двух недель — тоже подозрительно для «когда удобно созвониться».
    if d > (now + timedelta(days=14)).date():
        log.info("call_time: получена слишком далёкая дата %s, игнорируем", d)
        return None
    return d, t
