"""Данные для приложения «BONJOUR Салон» — личного кабинета администратора.

Правило то же, что у мастера (master_bot_service): к какому салону относится
сотрудник, решает сервер по карточке салона (salons.json, поле employees), а
не запрос из приложения. От точки здесь нужны название и часы работы:
приложение — кабинет (зарплата, график, авансы, имущество), а не рабочий
инструмент; выручка и заказы клиентов остаются в панели у руководителя.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)



@dataclass
class Point:
    """Точка, к которой приписан сотрудник."""
    id: str
    name: str
    code: str
    order_code: str
    address: str
    phone: str
    work_hours_weekday: str
    work_hours_weekend: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "code": self.code, "order_code": self.order_code,
            "address": self.address, "phone": self.phone,
            "work_hours_weekday": self.work_hours_weekday, "work_hours_weekend": self.work_hours_weekend,
        }


def resolve_point(employee_id: str | int) -> Optional[Point]:
    """Точка сотрудника — по списку employees в карточке салона.

    None означает «приложение салона этому человеку не показываем»: он не
    приписан ни к одной точке, и показать чужую выручку хуже, чем не показать
    ничего.
    """
    from app.data.salon_repository import get_salon_repository

    eid = str(employee_id)
    for salon in get_salon_repository().list_salons(status="active"):
        if eid in [str(x) for x in (getattr(salon, "employees", None) or [])]:
            return Point(
                id=salon.id,
                name=(salon.name or "").strip(),
                code=(salon.code or "").strip(),
                order_code=(salon.order_code or "").strip(),
                address=(salon.address or "").strip(),
                phone=(salon.phone or "").strip(),
                work_hours_weekday=(salon.work_hours_weekday or "").strip(),
                work_hours_weekend=(salon.work_hours_weekend or "").strip(),
            )
    return None


def shift_today(employee_id: str, point: Point, today: date | None = None) -> dict[str, Any]:
    """Открыта ли смена сегодня и во сколько её отметили.

    Отметка об открытии — та же, что приходит из бота (shift_checkins):
    фотография салона в начале смены. Здесь она только показывается.
    """
    from app.data.shift_checkin_repository import get_shift_checkin_repository

    day = (today or date.today()).isoformat()
    rows = get_shift_checkin_repository().list(date_from=day, date_to=day, employee_id=str(employee_id))
    mine = rows[0] if rows else None
    weekend = (today or date.today()).weekday() >= 5
    expected = (point.work_hours_weekend if weekend else point.work_hours_weekday or "").split("-")[0].strip()
    return {
        "date": day,
        "opened": bool(mine),
        "sent_at": (mine or {}).get("sent_at"),
        "delay_minutes": (mine or {}).get("delay_minutes"),
        "penalty_amount": (mine or {}).get("penalty_amount"),
        "expected_open_time": (mine or {}).get("expected_open_time") or expected or None,
        "photo": bool((mine or {}).get("photo_path")),
    }


def assets(employee_id: str) -> list[dict[str, Any]]:
    """Имущество, выданное этому сотруднику: форма, инструмент, техника."""
    from app.data.asset_repository import AssetRepository

    out = []
    for row in AssetRepository().list(employee_id=str(employee_id)):
        out.append({
            "id": row.get("id"),
            "name": row.get("item_name"),
            "size": row.get("size"),
            "quantity": row.get("quantity"),
            "issue_date": row.get("issue_date"),
            "return_date": row.get("return_date"),
            "service_life": row.get("service_life"),
            # Расписался ли сотрудник за выдачу — в панели это отдельная кнопка.
            "acked": bool(row.get("acked_at")),
        })
    return out
