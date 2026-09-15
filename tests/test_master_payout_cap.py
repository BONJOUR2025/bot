"""Лимит аванса мастера при заявке из кабинета и приложения: POST /api/payouts/.

Правила те же, что в Telegram-боте: больше заработанного за месяц минус уже
взятое попросить нельзя, но только когда сотрудник просит сам за себя, и
fail-open — если лимит сейчас не посчитать, заявка проходит к админу.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.api.payouts import create_payout_router
from app.schemas.payout import Payout
from app.services import master_bot_service as mbs
from app.services.access_control_service import ResolvedUser

MASTER = mbs.Master(employee_id="700", name="Корягин", position="Мастер по ремонту", agbis_user_id=110133)
CAP = {"earned": 10000.0, "advances": 7000.0, "available": 3000.0, "basis": "accrued"}


def _user(**kw):
    data = dict(
        id="700", login="koryagin", role_id="master", role_name="Мастер",
        permissions=[], bot_buttons=[], display_name="Константин К.",
        allowed_employee_ids=["700"], allowed_departments=None,
        employee_id="700", is_master=True,
    )
    data.update(kw)
    return ResolvedUser(**data)


def _body(**kw):
    data = dict(
        user_id="700", name="Корягин", phone="+7900", card_number="1234", bank="Сбер",
        amount=2000, method="💳 На карту", payout_type="Аванс",
    )
    data.update(kw)
    return data


@pytest.fixture
def state(monkeypatch):
    st = {"cap": CAP, "error": None, "master": MASTER, "cap_calls": 0}
    monkeypatch.setattr(mbs, "resolve_master", lambda eid: st["master"])

    def fake_cap(master):
        st["cap_calls"] += 1
        if st["error"]:
            raise st["error"]
        return st["cap"]

    monkeypatch.setattr(mbs, "get_advance_cap", fake_cap)
    return st


def _client(user):
    svc = AsyncMock()
    svc.create_payout.return_value = Payout(
        id="1", user_id="700", name="Корягин", phone="+7900", card_number="1234", bank="Сбер",
        amount=2000, method="💳 На карту", payout_type="Аванс", status="Ожидает",
        timestamp="2026-09-15 10:00:00",
    )
    access = MagicMock()
    access.is_employee_visible.return_value = True
    access.user_has_permission.side_effect = (
        lambda u, perm: "*" in u.permissions or perm in u.permissions
    )
    app = FastAPI()
    app.include_router(create_payout_router(svc, access), prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app), svc


def test_advance_above_cap_is_refused_with_available_amount(state):
    client, svc = _client(_user())
    resp = client.post("/api/payouts/", json=_body(amount=5000))
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "Доступно к авансу" in detail
    assert "3 000" in detail
    svc.create_payout.assert_not_awaited()


def test_advance_within_cap_goes_through(state):
    client, svc = _client(_user())
    assert client.post("/api/payouts/", json=_body(amount=2000)).status_code == 200
    svc.create_payout.assert_awaited_once()


def test_advance_equal_to_cap_is_allowed(state):
    client, _ = _client(_user())
    assert client.post("/api/payouts/", json=_body(amount=3000)).status_code == 200


def test_bonus_is_not_limited(state):
    client, _ = _client(_user())
    assert client.post("/api/payouts/", json=_body(amount=50000, payout_type="Премия")).status_code == 200
    assert state["cap_calls"] == 0


def test_request_for_another_employee_is_not_limited(state):
    """Заявку за другого заводит тот, у кого есть права, — это не самообслуживание."""
    client, _ = _client(_user())
    assert client.post("/api/payouts/", json=_body(user_id="701", amount=50000)).status_code == 200
    assert state["cap_calls"] == 0


def test_account_with_payouts_permission_is_not_limited(state):
    client, _ = _client(_user(permissions=["payouts"]))
    assert client.post("/api/payouts/", json=_body(amount=50000)).status_code == 200
    assert state["cap_calls"] == 0


def test_non_master_is_not_limited(state):
    state["master"] = None
    client, _ = _client(_user(is_master=False))
    assert client.post("/api/payouts/", json=_body(amount=50000)).status_code == 200


def test_cap_failure_lets_request_through(state):
    """Firebird занят — заявка уходит к админу, а не блокируется."""
    state["error"] = TimeoutError("firebird busy")
    client, svc = _client(_user())
    assert client.post("/api/payouts/", json=_body(amount=50000)).status_code == 200
    svc.create_payout.assert_awaited_once()
