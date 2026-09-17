"""Данные для приложения «BONJOUR Салон» — по одной точке и одному админу.

Почему отдельный модуль, а не расширение отчётов панели: там срез по всей
сети с правами на чужие деньги, здесь — одна точка, к которой человек
приписан, и только то, что ему нужно на смене. Правило то же, что у мастера
(master_bot_service): к какому салону относится сотрудник, решает сервер по
карточке, а не запрос из приложения.

Салон для сотрудника берётся из списка salons.json (поле employees). Заказы и
выручка привязываются к салону так же, как во всех соседних отчётах — по
суффиксу номера заказа («34247-7» → салон с order_code 7), а не по DEP_ID:
смешение двух правил даёт один и тот же заказ в разных салонах в разных
отчётах.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Статусы заказа в Агбисе (ORDER_STATUSES) — те же, что в master_scan_service.
STATUS_NEW = 1
STATUS_STORAGE = 2
STATUS_IN_WORK = 3
STATUS_DONE = 4
STATUS_ISSUED = 5
OPEN_STATUSES = (STATUS_NEW, STATUS_STORAGE, STATUS_IN_WORK, STATUS_DONE)


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


def _sales_rows(date_from: date, date_to: date, point: Point) -> list[dict[str, Any]]:
    from app.services.firebird_service import get_firebird_service

    return get_firebird_service().get_daily_sales(date_from, date_to, salon_ids=[point.id]) or []


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def sales(point: Point, today: date | None = None) -> dict[str, Any]:
    """Выручка точки: сегодня, вчера и с начала месяца, плюс по дням.

    Считается из того же отчёта, что «Продажи» в панели (get_daily_sales с
    фильтром по салону), поэтому цифры сходятся с тем, что видит руководитель.
    """
    today = today or date.today()
    month_start = today.replace(day=1)
    rows = _sales_rows(month_start, today, point)
    by_day: dict[str, float] = {}
    for row in rows:
        day = str(row.get("date") or "")[:10]
        if not day:
            continue
        by_day[day] = by_day.get(day, 0.0) + _num(row.get("total"))
    yesterday = (today - timedelta(days=1)).isoformat()
    days = [{"day": d, "total": round(v, 2)} for d, v in sorted(by_day.items())]
    month_total = round(sum(by_day.values()), 2)
    worked = len([d for d in days if d["total"] > 0])
    return {
        "today": round(by_day.get(today.isoformat(), 0.0), 2),
        "yesterday": round(by_day.get(yesterday, 0.0), 2),
        "month": month_total,
        "month_days": worked,
        "avg_day": round(month_total / worked, 2) if worked else 0.0,
        "days": days,
        "date_from": month_start.isoformat(),
        "date_to": today.isoformat(),
    }


def orders(point: Point, now: datetime | None = None, limit: int = 400) -> dict[str, Any]:
    """Невыданные заказы точки — двумя стопками: готовые и ещё в работе.

    Готовый заказ, у которого срок прошёл, — это не просрочка мастерской, а
    вещь, за которой не пришёл клиент: у «Гранд Паласа» таких 141 из 232.
    Мешать их с горящими работами нельзя, поэтому у каждой строки есть kind
    («ready» или «work»), а счётчики считаются по своим стопкам.

    Код салона в номере заказа не уникален (в 2026-м «7» носят и Пассаж, и
    Гранд Палас), поэтому после выборки строки прогоняются через тот же
    определитель салона по дате, что и отчёты панели.
    """
    from app.services.firebird_service import FIREBIRD_AVAILABLE, _SalonResolver, _connect

    now = now or datetime.now()
    empty = {"ready": [], "work": [], "counts": {"ready": 0, "overdue": 0, "today": 0, "work": 0}}
    if not FIREBIRD_AVAILABLE or not point.order_code:
        return empty

    sql = """
        SELECT FIRST ?
            d.doc_num, d.doc_date, d.contragent_id, c.name, c.teleph_cell,
            dor.status_id, dor.date_out, dor.kredit,
            (SELECT COUNT(*) FROM doc_order_serv_photos p
                INNER JOIN doc_order_services s ON s.id = p.dos_id
                WHERE s.doc_order_id = dor.id)
        FROM docs d
            INNER JOIN docs_order dor ON dor.doc_id = d.doc_id
            LEFT JOIN contragents c ON c.contr_id = d.contragent_id
        WHERE d.doc_num LIKE ? AND dor.status_id IN (1, 2, 3, 4) AND d.doc_date >= ?
        ORDER BY dor.date_out
    """
    since = now.date() - timedelta(days=365)
    try:
        con = _connect()
        try:
            cur = con.cursor()
            cur.execute(sql, (int(limit), f"%-{point.order_code}", since))
            rows = cur.fetchall()
        finally:
            con.close()
    except Exception:
        logger.exception("Не удалось получить заказы точки %s", point.name)
        return empty

    ready: list[dict[str, Any]] = []
    work: list[dict[str, Any]] = []
    with _SalonResolver() as resolve_salon:
        for doc_num, doc_date, contr_id, client, phone, status_id, date_out, kredit, photos in rows:
            doc_num = (doc_num or "").strip()
            if resolve_salon(doc_num, doc_date) not in (point.id, None):
                continue
            due = date_out if isinstance(date_out, datetime) and date_out.year > 2000 else None
            item = {
                "doc_num": doc_num,
                "doc_date": doc_date.isoformat() if hasattr(doc_date, "isoformat") else None,
                "client": (client or "").strip() or "—",
                "phone": (phone or "").strip(),
                "contragent_id": contr_id,
                "status_id": status_id,
                "kredit": _num(kredit),
                "due": due.isoformat(timespec="minutes") if due else None,
                "photos": int(photos or 0),
            }
            if status_id == STATUS_DONE:
                # Сколько дней вещь ждёт клиента — считаем от обещанной даты:
                # именно с неё заказ можно было забрать.
                item["kind"] = "ready"
                item["waiting_days"] = max((now.date() - due.date()).days, 0) if due else None
                ready.append(item)
            else:
                item["kind"] = "work"
                item.update(_due_state(due, now))
                work.append(item)

    ready.sort(key=lambda r: -(r["waiting_days"] or 0))
    rank = {"overdue": 0, "today": 1, "tomorrow": 2}
    work.sort(key=lambda r: (rank.get(r["due_state"], 3), -(r["overdue_days"] or 0), r["due"] or ""))
    return {
        "ready": ready,
        "work": work,
        "counts": {
            "ready": len(ready),
            "overdue": sum(1 for r in work if r["due_state"] == "overdue"),
            "today": sum(1 for r in work if r["due_state"] == "today"),
            "work": len(work),
        },
    }


def _due_state(due: Optional[datetime], now: datetime) -> dict[str, Any]:
    """Где обещанная дата относительно «сейчас» — как в «В работе» у мастера."""
    if due is None:
        return {"due_state": None, "overdue_days": None}
    if due < now:
        return {"due_state": "overdue", "overdue_days": max((now.date() - due.date()).days, 0)}
    if due.date() == now.date():
        return {"due_state": "today", "overdue_days": None}
    if due.date() == now.date() + timedelta(days=1):
        return {"due_state": "tomorrow", "overdue_days": None}
    return {"due_state": None, "overdue_days": None}


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
