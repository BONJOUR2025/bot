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


async def check_and_notify() -> None:
    from app.data.mdm_repository import get_mdm_repository
    from app.services.notify import send_notification

    repo = get_mdm_repository()
    now = datetime.now(timezone.utc)

    gone: list[dict[str, Any]] = []
    back: list[dict[str, Any]] = []

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

    if gone:
        lines = "\n".join(_silence_text(d, now) for d in gone)
        word = "телефон" if len(gone) == 1 else "телефонов"
        # Одно сообщение на всех, а не по штуке: когда падает туннель, молчат
        # сразу все аппараты, и россыпь одинаковых уведомлений только мешает.
        # Категория «СБОЙ», а не «к сведению»: замолчавший телефон — это либо
        # сломанная связь, либо унесённый аппарат, и то и другое требует
        # действий. Префиксы — общая конвенция ленты, см. tests/test_notification_tiers.py.
        await send_notification(
            f"🛠 <b>СБОЙ · Не выходят на связь: {len(gone)} {word}</b>
{lines}

"
            f"Если молчат все сразу — скорее всего дело не в телефонах, а в туннеле."
        )

    if back:
        lines = "\n".join(f"• {_title(d)}" for d in back)
        await send_notification(f"⚪ <b>Телефоны снова на связи</b>\n{lines}")
