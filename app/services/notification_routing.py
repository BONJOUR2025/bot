"""Кому и какие уведомления основного бота уходят.

Раньше всё служебное летело одному человеку — в notification_chat_id
(уведомления системы и подбора) или в ADMIN_CHAT_ID (заявки из бота). Теперь
уведомления разбиты на группы, у каждой — свой выключатель и свой список
получателей (Telegram ID или @username): запросы на выплаты одному, сообщения кандидатов
другому и т. д.

Группа, которую ещё не настраивали, шлёт туда же, куда и раньше
(notification_chat_id, а если он пуст — ADMIN_CHAT_ID). Поэтому пустой или
отсутствующий файл настроек ничего не меняет в поведении.

Хранится в NOTIFICATION_ROUTING_FILE (JSON в рабочей папке продакшна):
    {"groups": {"payouts": {"enabled": true, "recipients": [5495663985]}, ...}}
Перечитывается на каждой отправке — так правка в админке действует сразу
во всех трёх процессах (бот, API, ВК), без перезапуска.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

log = logging.getLogger(__name__)

# Порядок — как на странице настроек.
GROUPS: list[dict[str, str]] = [
    {"key": "payouts", "label": "Запросы на выплаты",
     "description": "Сотрудник запросил аванс или зарплату — с кнопками «Одобрить» и «Отклонить»."},
    {"key": "employee_changes", "label": "Изменение данных сотрудников",
     "description": "Сотрудник хочет поменять телефон, карту и т. п. в личном кабинете — нужно одобрить."},
    {"key": "employee_messages", "label": "Сообщения от сотрудников",
     "description": "Сотрудник написал руководству через бота."},
    {"key": "candidate_messages", "label": "Сообщения кандидатов",
     "description": "Кандидат задал вопрос, прошёл опрос или бот не смог ему написать — нужен ответ на площадке."},
    {"key": "candidates_new", "label": "Новые отклики",
     "description": "Сводки новых откликов с hh.ru и Авито, кто молчит сутки, сбои загрузки откликов."},
    {"key": "workshop", "label": "Цех",
     "description": "Отметки входа и выхода через старшего мастера, деление услуг между мастерами."},
    {"key": "finance", "label": "Финансы",
     "description": "Напоминания о платежах по календарю, привязка выплат к кассовым перемещениям."},
    {"key": "digest", "label": "Сводки и праздники",
     "description": "Утренняя сводка, дни рождения сотрудников, первый заказ клиента."},
    {"key": "system", "label": "Сбои и техника",
     "description": "Что-то сломалось: телефоны салонов не на связи, не доставлено сообщение, отключился Secretary Mode."},
]
GROUP_KEYS = {g["key"] for g in GROUPS}
DEFAULT_GROUP = "system"


def _path() -> str:
    from app.config import NOTIFICATION_ROUTING_FILE

    return NOTIFICATION_ROUTING_FILE


def load() -> dict[str, Any]:
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        log.warning("notification_routing: файл не прочитан (%s) — работают значения по умолчанию", exc)
        return {}


def save(data: dict[str, Any]) -> None:
    path = _path()
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def default_recipient() -> int | None:
    """Куда шло всё до разделения на группы."""
    try:
        from app.services.config_service import ConfigService

        raw = str(ConfigService().load().get("notification_chat_id") or "").strip()
        if raw.lstrip("-").isdigit():
            return int(raw)
    except Exception:
        pass
    try:
        from app.config import ADMIN_CHAT_ID

        return int(ADMIN_CHAT_ID) if ADMIN_CHAT_ID else None
    except Exception:
        return None


def group_settings(group: str) -> dict[str, Any]:
    """{"enabled", "recipients", "configured"} для группы с учётом умолчаний."""
    if group not in GROUP_KEYS:
        group = DEFAULT_GROUP
    cfg = (load().get("groups") or {}).get(group)
    if not isinstance(cfg, dict):
        default = default_recipient()
        return {"enabled": True, "recipients": [default] if default else [], "configured": False}
    recipients: list[int | str] = []
    for r in cfg.get("recipients") or []:
        if isinstance(r, str) and normalize_username(r):
            recipients.append(normalize_username(r))
            continue
        try:
            recipients.append(int(r))
        except (TypeError, ValueError):
            continue
    return {"enabled": bool(cfg.get("enabled", True)), "recipients": recipients, "configured": True}


# ── получатель по @username ────────────────────────────────────────────
# Telegram не даёт боту узнать ID человека по username и не даёт написать
# тому, кто бота не запускал. Поэтому @username сверяется со списком тех, кто
# писал боту (bot_users.json): нашёлся — в настройки ложится ID; нет —
# хранится «@username» и превращается в ID на каждой отправке, как только
# человек нажмёт «Старт».
USERNAME_RE = re.compile(r"^@?([A-Za-z][A-Za-z0-9_]{3,31})$")


def normalize_username(value: Any) -> str | None:
    m = USERNAME_RE.match(str(value or "").strip())
    return f"@{m.group(1).lower()}" if m else None


def resolve_username(value: Any) -> int | None:
    name = normalize_username(value)
    if not name:
        return None
    try:
        from app.data.bot_user_repository import get_bot_user_repository

        for u in get_bot_user_repository().list():
            if (u.get("username") or "").lower() == name[1:]:
                tid = str(u.get("telegram_id") or "")
                return int(tid) if tid.lstrip("-").isdigit() else None
    except Exception:
        log.warning("notification_routing: список пользователей бота не прочитан", exc_info=True)
    return None


def recipients(group: str) -> list[int]:
    """Кому отправлять уведомление группы; [] — группа выключена или пуста.
    @username, который ещё не писал боту, пропускается."""
    s = group_settings(group)
    if not s["enabled"]:
        return []
    seen: list[int] = []
    for r in s["recipients"]:
        if isinstance(r, str):
            r = resolve_username(r)
            if r is None:
                continue
        if r not in seen:
            seen.append(r)
    return seen
