"""Кабинет администратора точки: /api/salon/me/* отдаёт только свою точку.

Главное здесь то же, что у мастера: точка берётся из карточки по сессии, а не
из запроса, и сотрудник без точки не видит ничего.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.api.salon_self import create_salon_self_router
from app.services import salon_self_service as sss
from app.services.access_control_service import ResolvedUser

POINT = sss.Point(
    id="salon-7", name="Пассаж", code="П", order_code="7",
    address="Невский пр., 48", phone="+7 812 000-00-00",
    work_hours_weekday="10:00-22:00", work_hours_weekend="11:00-22:00",
)
NOW = datetime(2026, 9, 17, 15, 0)


def _user(**kw):
    data = dict(
        id="500", login="admin7", role_id="employee_checkin", role_name="Администратор",
        permissions=[], bot_buttons=[], display_name="Иванова А.",
        allowed_employee_ids=["500"], allowed_departments=None, employee_id="500",
    )
    data.update(kw)
    return ResolvedUser(**data)


def _client(user=None):
    app = FastAPI()
    app.include_router(create_salon_self_router(), prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: user or _user()
    return TestClient(app)


# ── Какая точка моя ───────────────────────────────────────────────

class _Salon:
    def __init__(self, sid, employees, status="active", **kw):
        self.id, self.employees, self.status = sid, employees, status
        self.name = kw.get("name", "Точка")
        self.code = kw.get("code", "П")
        self.order_code = kw.get("order_code", "7")
        self.address = self.phone = ""
        self.work_hours_weekday = "10:00-22:00"
        self.work_hours_weekend = "11:00-22:00"


def _salons(monkeypatch, salons):
    class _Repo:
        def list_salons(self, status=None):
            return [s for s in salons if not status or s.status == status]

    monkeypatch.setattr("app.data.salon_repository.get_salon_repository", lambda: _Repo())


def test_point_comes_from_the_salon_card(monkeypatch):
    _salons(monkeypatch, [_Salon("a", ["1"]), _Salon("b", ["500", "9"], name="Пассаж")])
    point = sss.resolve_point("500")
    assert point.id == "b" and point.name == "Пассаж"


def test_employee_without_a_point_sees_nothing(monkeypatch):
    _salons(monkeypatch, [_Salon("a", ["1"])])
    assert sss.resolve_point("500") is None
    resp = _client().get("/api/salon/me/point")
    assert resp.status_code == 404 and resp.json()["detail"] == "not_on_a_point"


def test_closed_point_is_not_mine(monkeypatch):
    _salons(monkeypatch, [_Salon("a", ["500"], status="closed")])
    assert sss.resolve_point("500") is None


# ── Смена ─────────────────────────────────────────────────────────

def _checkins(monkeypatch, rows):
    class _Repo:
        def list(self, date_from=None, date_to=None, salon_id=None, employee_id=None):
            return rows

    monkeypatch.setattr("app.data.shift_checkin_repository.get_shift_checkin_repository", lambda: _Repo())


def test_shift_not_opened_yet(monkeypatch):
    _checkins(monkeypatch, [])
    shift = sss.shift_today("500", POINT, today=date(2026, 9, 17))   # четверг
    assert shift["opened"] is False and shift["expected_open_time"] == "10:00"


def test_shift_opened_with_delay(monkeypatch):
    _checkins(monkeypatch, [{"sent_at": "2026-09-17T10:12:00+03:00", "delay_minutes": 12,
                             "penalty_amount": 300, "photo_path": "shift/1.jpg",
                             "expected_open_time": "10:00"}])
    shift = sss.shift_today("500", POINT, today=date(2026, 9, 17))
    assert shift["opened"] and shift["delay_minutes"] == 12 and shift["photo"] is True


def test_weekend_opening_time_comes_from_the_weekend_hours(monkeypatch):
    _checkins(monkeypatch, [])
    shift = sss.shift_today("500", POINT, today=date(2026, 9, 19))   # суббота
    assert shift["expected_open_time"] == "11:00"


# ── Выручка ───────────────────────────────────────────────────────

def test_sales_sum_by_day_and_month(monkeypatch):
    rows = [
        {"date": "2026-09-16", "total": 12000}, {"date": "2026-09-16", "total": 3000},
        {"date": "2026-09-17", "total": 5000},
    ]
    monkeypatch.setattr(sss, "_sales_rows", lambda df, dt, point: rows)
    out = sss.sales(POINT, today=date(2026, 9, 17))
    assert out["today"] == 5000 and out["yesterday"] == 15000
    assert out["month"] == 20000 and out["month_days"] == 2 and out["avg_day"] == 10000
    assert [d["day"] for d in out["days"]] == ["2026-09-16", "2026-09-17"]


def test_sales_without_a_single_order(monkeypatch):
    monkeypatch.setattr(sss, "_sales_rows", lambda df, dt, point: [])
    out = sss.sales(POINT, today=date(2026, 9, 17))
    assert out == {"today": 0.0, "yesterday": 0.0, "month": 0, "month_days": 0, "avg_day": 0.0,
                   "days": [], "date_from": "2026-09-01", "date_to": "2026-09-17"}


# ── Заказы точки ──────────────────────────────────────────────────

def _orders_db(monkeypatch, rows):
    class _Cur:
        def execute(self, sql, params=()):
            self.params = params

        def fetchall(self):
            return rows

    class _Con:
        def cursor(self):
            return _Cur()

        def close(self):
            pass

    monkeypatch.setattr("app.services.firebird_service.FIREBIRD_AVAILABLE", True, raising=False)
    monkeypatch.setattr("app.services.firebird_service._connect", lambda: _Con())


def _row(num, status, due, photos=0):
    # Колонки — как в запросе: номер, дата, клиент, телефон, статус, срок, сумма, фото.
    return (num, date(2026, 9, 1), 42, "Клиент", "+79990000000", status, due, 1500, photos)


def _resolver(monkeypatch, mapping=None):
    """Определитель салона по номеру заказа: у кодов бывают двойники."""
    class _R:
        def __enter__(self):
            return lambda doc_num, doc_date: (mapping or {}).get(doc_num, POINT.id)

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("app.services.firebird_service._SalonResolver", _R)


def test_ready_orders_are_separate_from_work(monkeypatch):
    _orders_db(monkeypatch, [
        _row("10001-7", 3, datetime(2026, 9, 25, 19, 0)),          # в работе, срок не горит
        _row("10002-7", 3, datetime(2026, 9, 12, 19, 0)),          # в работе, просрочен
        _row("10003-7", 4, datetime(2026, 3, 20, 19, 0), 3),       # готов, клиент не забрал
        _row("10004-7", 3, datetime(2026, 9, 17, 19, 0)),          # в работе, сегодня
        _row("10005-7", 4, datetime(2026, 9, 16, 19, 0)),          # готов вчера
    ])
    _resolver(monkeypatch)
    out = sss.orders(POINT, now=NOW)
    assert [r["doc_num"] for r in out["ready"]] == ["10003-7", "10005-7"]
    assert [r["doc_num"] for r in out["work"]] == ["10002-7", "10004-7", "10001-7"]
    assert out["counts"] == {"ready": 2, "overdue": 1, "today": 1, "work": 3}
    assert out["ready"][0]["waiting_days"] == 181      # ждёт с 20 марта
    assert out["work"][0]["overdue_days"] == 5
    assert out["ready"][0]["photos"] == 3


def test_orders_of_a_point_sharing_the_same_code_are_filtered_out(monkeypatch):
    """«7» носят и Пассаж, и Гранд Палас — чужие заказы показывать нельзя."""
    _orders_db(monkeypatch, [
        _row("20001-7", 3, datetime(2026, 9, 12, 19, 0)),
        _row("20002-7", 3, datetime(2026, 9, 12, 19, 0)),
    ])
    _resolver(monkeypatch, {"20002-7": "another-salon"})
    out = sss.orders(POINT, now=NOW)
    assert [r["doc_num"] for r in out["work"]] == ["20001-7"]


def test_orders_ask_agbis_for_this_point_only(monkeypatch):
    seen = {}

    class _Cur:
        def execute(self, sql, params=()):
            seen["params"] = params

        def fetchall(self):
            return []

    class _Con:
        def cursor(self):
            return _Cur()

        def close(self):
            pass

    monkeypatch.setattr("app.services.firebird_service.FIREBIRD_AVAILABLE", True, raising=False)
    monkeypatch.setattr("app.services.firebird_service._connect", lambda: _Con())
    _resolver(monkeypatch)
    sss.orders(POINT, now=NOW)
    assert "%-7" in seen["params"]


def test_orders_survive_agbis_being_down(monkeypatch):
    monkeypatch.setattr("app.services.firebird_service.FIREBIRD_AVAILABLE", True, raising=False)

    def boom():
        raise RuntimeError("Агбис молчит")

    monkeypatch.setattr("app.services.firebird_service._connect", boom)
    out = sss.orders(POINT, now=NOW)
    assert out["ready"] == [] and out["work"] == [] and out["counts"]["ready"] == 0


# ── API ───────────────────────────────────────────────────────────

def test_point_endpoint_returns_point_and_shift(monkeypatch):
    _salons(monkeypatch, [_Salon("b", ["500"], name="Пассаж")])
    _checkins(monkeypatch, [])
    body = _client().get("/api/salon/me/point").json()
    assert body["point"]["name"] == "Пассаж" and body["shift"]["opened"] is False


def test_account_without_an_employee_card_is_refused(monkeypatch):
    resp = _client(_user(employee_id=None)).get("/api/salon/me/point")
    assert resp.status_code == 403 and resp.json()["detail"] == "not_an_employee"


def test_sales_endpoint_uses_the_point_from_the_session(monkeypatch):
    _salons(monkeypatch, [_Salon("b", ["500"], name="Пассаж")])
    asked = {}

    def fake_sales(point):
        asked["id"] = point.id
        return {"today": 1.0}

    monkeypatch.setattr(sss, "sales", fake_sales)
    body = _client().get("/api/salon/me/sales").json()
    assert body == {"today": 1.0} and asked["id"] == "b"


def test_assets_are_listed_for_the_signed_in_employee(monkeypatch):
    asked = {}

    def fake_assets(employee_id):
        asked["eid"] = employee_id
        return [{"id": 1, "name": "Термопот"}]

    monkeypatch.setattr(sss, "assets", fake_assets)
    body = _client().get("/api/salon/me/assets").json()
    assert body["items"][0]["name"] == "Термопот" and asked["eid"] == "500"
