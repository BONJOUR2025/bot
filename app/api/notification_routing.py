"""Настройки уведомлений основного бота: группы, выключатели, получатели.

Сама маршрутизация — app/services/notification_routing.py. Здесь — чтение
и запись настроек для страницы «Настройки → Уведомления», справочник людей,
которых можно выбрать получателями, и тестовая отправка в группу.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .dependencies import require_permission


class GroupIn(BaseModel):
    enabled: bool = True
    recipients: list[int] = []


class RoutingIn(BaseModel):
    groups: dict[str, GroupIn]


def _people() -> dict[int, dict[str, str]]:
    """Кого можно выбрать получателем: сотрудники с привязанным Telegram и
    те, кто писал боту. ID → {"name", "hint"}."""
    from app.data.bot_user_repository import get_bot_user_repository
    from app.data.employee_repository import EmployeeRepository
    from app.utils import is_valid_user_id

    out: dict[int, dict[str, str]] = {}
    for e in EmployeeRepository().list_employees(archived=False):
        if is_valid_user_id(e.id):
            out[int(e.id)] = {"name": (e.full_name or e.name or "").strip() or f"ID {e.id}",
                              "hint": str(getattr(e, "position", "") or "сотрудник")}
    try:
        for u in get_bot_user_repository().list():
            tid = str(u.get("telegram_id") or "")
            if not is_valid_user_id(tid) or int(tid) in out:
                continue
            name = " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x).strip()
            uname = f"@{u['username']}" if u.get("username") else ""
            out[int(tid)] = {"name": name or uname or f"ID {tid}", "hint": uname or "писал боту"}
    except Exception:
        pass
    return out


def create_notification_routing_router() -> APIRouter:
    router = APIRouter(
        prefix="/notification-routing",
        tags=["Уведомления"],
        dependencies=[Depends(require_permission("settings"))],
    )

    @router.get("")
    async def get_routing() -> dict[str, Any]:
        from app.services import notification_routing as nr

        people = _people()

        def person(pid: int) -> dict[str, Any]:
            p = people.get(pid) or {"name": f"ID {pid}", "hint": "нет в списке сотрудников"}
            return {"id": pid, **p}

        default = nr.default_recipient()
        groups = []
        for g in nr.GROUPS:
            s = nr.group_settings(g["key"])
            groups.append({**g, "enabled": s["enabled"], "configured": s["configured"],
                           "recipients": [person(r) for r in s["recipients"]]})
        return {
            "groups": groups,
            "default_recipient": person(default) if default else None,
            "people": sorted(({"id": k, **v} for k, v in people.items()), key=lambda p: p["name"].lower()),
        }

    @router.put("")
    async def put_routing(data: RoutingIn) -> dict[str, Any]:
        from app.services import notification_routing as nr

        unknown = set(data.groups) - nr.GROUP_KEYS
        if unknown:
            raise HTTPException(400, "Неизвестные группы: " + ", ".join(sorted(unknown)))
        doc = nr.load()
        groups = doc.setdefault("groups", {})
        for key, g in data.groups.items():
            bad = [r for r in g.recipients if r <= 0]
            if bad:
                raise HTTPException(400, f"Некорректный Telegram ID: {bad[0]}")
            uniq: list[int] = []
            for r in g.recipients:
                if r not in uniq:
                    uniq.append(r)
            groups[key] = {"enabled": g.enabled, "recipients": uniq}
        nr.save(doc)
        return {"saved": True}

    @router.post("/test/{group}")
    async def test_group(group: str) -> dict[str, Any]:
        from app.services import notification_routing as nr
        from app.services.notify import notify_group

        if group not in nr.GROUP_KEYS:
            raise HTTPException(404, "Неизвестная группа")
        label = next(g["label"] for g in nr.GROUPS if g["key"] == group)
        chat_ids = nr.recipients(group)
        if not chat_ids:
            raise HTTPException(400, "Группа выключена или в ней нет получателей")
        ok = await notify_group(group, f"✅ <b>Тест уведомлений · {label}</b>\n"
                                       f"Сюда будут приходить уведомления этой группы.")
        if not ok:
            raise HTTPException(502, "Telegram не принял сообщение — проверьте, что получатель запускал бота")
        return {"sent": True, "recipients": chat_ids}

    return router
