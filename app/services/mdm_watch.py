"""Сторож молчащих телефонов под MDM.

Панель подсвечивает аппарат, который давно не выходил на связь, но смотреть в
панель круглосуточно некому. Телефон, замолчавший потому, что его унесли,
обнаружится через неделю — когда это уже не поможет.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)

# Телефон опрашивает команды раз в две минуты и делает полный чек-ин раз в 15.
# Час молчания — это уже не «не успел» и не всплеск на линии.
SILENCE_MINUTES = 60

# Повторно напоминать про тот же телефон не чаще, чем раз в шесть часов: если
# аппарат увезли, сообщение каждые десять минут не добавит ни знания, ни
# скорости, а нужное потонет в шуме.
RENOTIFY_HOURS = 6

# Поле служебное, в схему MdmDevice не входит: наружу его отдавать незачем,
# а pydantic лишние ключи из хранилища молча игнорирует.
ALERT_FIELD = "silence_alerted_at"

# Поле с отпечатком последней тревоги о здоровье — чтобы не слать одно и то же
# каждые 10 минут. Хранит набор сработавших правил и когда.
HEALTH_ALERT_FIELD = "health_alerted"

# Пороги здоровья.
LOW_STORAGE_PERCENT = 10   # свободно меньше — предупредить
LOW_BATTERY_PERCENT = 15   # заряд ниже — предупредить (телефон на связи, но вот-вот сядет)


def _parse(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _title(device: dict[str, Any]) -> str:
    name = device.get("name")
    if name:
        return str(name)
    model = " ".join(x for x in (device.get("manufacturer"), device.get("model")) if x)
    return model or str(device.get("id"))


def _silence_text(device: dict[str, Any], now: datetime) -> str:
    last = _parse(device.get("last_seen_at"))
    if last is None:
        return f"• {_title(device)} — ни разу не выходил на связь"
    hours = (now - last).total_seconds() / 3600
    when = f"{hours:.0f} ч" if hours >= 1 else f"{(now - last).total_seconds() / 60:.0f} мин"
    return f"• {_title(device)} — молчит {when} (последний раз в {last.astimezone().strftime('%H:%M %d.%m')})"


def _check_health(repo, device: dict[str, Any], now: datetime, out: list[str]) -> None:
    """Собирает поводы для тревоги по одному телефону и гасит повтор.

    Один отпечаток на телефон: пока набор сработавших правил не изменился,
    заново не тревожим (иначе каждые 10 минут одно и то же). Изменился —
    сообщаем свежий набор.
    """
    problems: list[str] = []

    free = device.get("storage_free_mb")
    total = device.get("storage_total_mb")
    if isinstance(free, int) and isinstance(total, int) and total > 0:
        if free * 100 / total < LOW_STORAGE_PERCENT:
            problems.append("мало места (" + str(round(free / 1024, 1)) + " ГБ)")

    battery = device.get("battery")
    if isinstance(battery, int) and battery < LOW_BATTERY_PERCENT:
        problems.append("низкий заряд (" + str(battery) + "%)")

    if device.get("secure_lock") is False:
        problems.append("нет пароля на экране")

    if device.get("device_owner") is False:
        problems.append("агент не владелец устройства")

    key = ",".join(sorted(problems))
    prev = device.get(HEALTH_ALERT_FIELD)
    if not problems:
        if prev:
            repo.upsert(str(device.get("id")), {HEALTH_ALERT_FIELD: None})
        return
    if prev == key:
        return  # тот же набор проблем уже показан
    repo.upsert(str(device.get("id")), {HEALTH_ALERT_FIELD: key})
    out.append("• " + _title(device) + ": " + "; ".join(problems))


async def check_and_notify() -> None:
    from app.data.mdm_repository import get_mdm_repository
    from app.services.notify import send_notification

    repo = get_mdm_repository()
    now = datetime.now(timezone.utc)

    gone: list[dict[str, Any]] = []
    back: list[dict[str, Any]] = []
    health_alerts: list[str] = []

    for device in repo.list():
        device_id = str(device.get("id"))
        last = _parse(device.get("last_seen_at"))
        alerted = _parse(device.get(ALERT_FIELD))
        silent = last is None or (now - last) > timedelta(minutes=SILENCE_MINUTES)

        if silent:
            if alerted is None or (now - alerted) > timedelta(hours=RENOTIFY_HOURS):
                gone.append(device)
                repo.upsert(device_id, {ALERT_FIELD: now.isoformat()})
        elif alerted is not None:
            # Сообщаем и о возвращении: без этого тревога остаётся висеть в
            # голове, а сама по себе она не снимается.
            back.append(device)
            repo.upsert(device_id, {ALERT_FIELD: None})

        # Проверки здоровья — только для телефонов на связи (молчащие уже
        # попали в тревогу выше, и их телеметрия устарела).
        if not silent:
            _check_health(repo, device, now, health_alerts)

    if gone:
        lines = "\n".join(_silence_text(d, now) for d in gone)
        word = "телефон" if len(gone) == 1 else "телефонов"
        # Одно сообщение на всех, а не по штуке: когда падает туннель, молчат
        # сразу все аппараты, и россыпь одинаковых уведомлений только мешает.
        # Категория «СБОЙ», а не «к сведению»: замолчавший телефон — это либо
        # сломанная связь, либо унесённый аппарат, и то и другое требует
        # действий. Префиксы — общая конвенция ленты, см. tests/test_notification_tiers.py.
        await send_notification(
            f"🛠 <b>СБОЙ · Не выходят на связь: {len(gone)} {word}</b>\n{lines}\n\n"
            f"Если молчат все сразу — скорее всего дело не в телефонах, а в туннеле."
        )

    if back:
        lines = "\n".join(f"• {_title(d)}" for d in back)
        await send_notification(f"⚪ <b>Телефоны снова на связи</b>\n{lines}")
