"""Кабинет администратора точки: /api/salon/me/* отдаёт только свою точку.

Главное здесь то же, что у мастера: точка берётся из карточки по сессии, а не
из запроса, и сотрудник без точки не видит ничего.
"""
from __future__ import annotations

from datetime import date

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


# ── API ───────────────────────────────────────────────────────────

def test_point_endpoint_returns_point_and_shift(monkeypatch):
    _salons(monkeypatch, [_Salon("b", ["500"], name="Пассаж")])
    _checkins(monkeypatch, [])
    body = _client().get("/api/salon/me/point").json()
    assert body["point"]["name"] == "Пассаж" and body["shift"]["opened"] is False


def test_account_without_an_employee_card_is_refused(monkeypatch):
    resp = _client(_user(employee_id=None)).get("/api/salon/me/point")
    assert resp.status_code == 403 and resp.json()["detail"] == "not_an_employee"


def test_work_tools_of_the_point_are_not_exposed(monkeypatch):
    """Кабинет — не рабочий инструмент: выручки и заказов точки здесь нет."""
    _salons(monkeypatch, [_Salon("b", ["500"], name="Пассаж")])
    client = _client()
    assert client.get("/api/salon/me/sales").status_code == 404
    assert client.get("/api/salon/me/orders").status_code == 404


def test_assets_are_listed_for_the_signed_in_employee(monkeypatch):
    asked = {}

    def fake_assets(employee_id):
        asked["eid"] = employee_id
        return [{"id": 1, "name": "Термопот"}]

    monkeypatch.setattr(sss, "assets", fake_assets)
    body = _client().get("/api/salon/me/assets").json()
    assert body["items"][0]["name"] == "Термопот" and asked["eid"] == "500"
