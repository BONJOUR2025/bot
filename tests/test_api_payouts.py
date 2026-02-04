"""Comprehensive tests for API payout endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.payouts import create_payout_router
from app.api.dependencies import get_current_user
from app.schemas.payout import Payout
from app.services.access_control_service import ResolvedUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolved(**kw):
    defaults = dict(
        id="admin", login="admin", role_id="owner", role_name="Owner",
        permissions=["*"], bot_buttons=["*"], display_name="Admin",
        allowed_employee_ids=None, allowed_departments=None,
    )
    defaults.update(kw)
    return ResolvedUser(**defaults)


def _payout(**kw):
    defaults = dict(
        id="1", user_id="100", name="Иван", phone="+7900",
        card_number="1234", bank="Сбер", amount=5000,
        method="💳 На карту", payout_type="Аванс",
        status="Ожидает", timestamp="2025-01-15 10:00:00",
    )
    defaults.update(kw)
    return Payout(**defaults)


def _make_app():
    payout_svc = AsyncMock()
    access_svc = MagicMock()
    access_svc.visible_employee_ids.return_value = None  # no restrictions
    access_svc.is_employee_visible.return_value = True
    access_svc.user_has_permission.return_value = True

    app = FastAPI()
    router = create_payout_router(payout_svc, access_svc)
    app.include_router(router, prefix="/api")
    return app, payout_svc, access_svc


def _client(app, user=None):
    u = user or _resolved()
    app.dependency_overrides[get_current_user] = lambda: u
    return TestClient(app)


# ===========================================================================
# GET /api/payouts/
# ===========================================================================

class TestListPayouts:
    def test_list_all(self):
        app, psvc, asvc = _make_app()
        psvc.list_payouts.return_value = [_payout()]
        c = _client(app)

        resp = c.get("/api/payouts/")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_with_filters(self):
        app, psvc, asvc = _make_app()
        psvc.list_payouts.return_value = []
        c = _client(app)

        resp = c.get("/api/payouts/?employee_id=100&status=Ожидает")
        assert resp.status_code == 200
        psvc.list_payouts.assert_called_once_with("100", None, "Ожидает", None, None, None)

    def test_list_scoped_user_blocked_employee(self):
        app, psvc, asvc = _make_app()
        asvc.visible_employee_ids.return_value = {"200"}
        c = _client(app)

        resp = c.get("/api/payouts/?employee_id=100")
        assert resp.status_code == 200
        assert resp.json() == []


# ===========================================================================
# POST /api/payouts/
# ===========================================================================

class TestCreatePayout:
    def test_create_success(self):
        app, psvc, asvc = _make_app()
        psvc.create_payout.return_value = _payout()
        c = _client(app)

        resp = c.post("/api/payouts/", json={
            "user_id": "100", "name": "Иван", "phone": "+7900",
            "bank": "Сбер", "amount": 5000, "method": "💳 На карту",
            "payout_type": "Аванс", "sync_to_bot": False,
        })
        assert resp.status_code == 200

    def test_create_forbidden_employee(self):
        app, psvc, asvc = _make_app()
        asvc.is_employee_visible.return_value = False
        c = _client(app)

        resp = c.post("/api/payouts/", json={
            "user_id": "100", "name": "Иван", "phone": "+7900",
            "bank": "Сбер", "amount": 5000, "method": "💳 На карту",
            "payout_type": "Аванс", "sync_to_bot": False,
        })
        assert resp.status_code == 403

    def test_create_with_timestamp_no_permission(self):
        app, psvc, asvc = _make_app()
        asvc.user_has_permission.return_value = False
        c = _client(app)

        resp = c.post("/api/payouts/", json={
            "user_id": "100", "name": "Иван", "phone": "+7900",
            "bank": "Сбер", "amount": 5000, "method": "💳 На карту",
            "payout_type": "Аванс", "sync_to_bot": False,
            "timestamp": "2025-01-15 10:00:00",
        })
        assert resp.status_code == 403


# ===========================================================================
# PUT /api/payouts/{id}
# ===========================================================================

class TestUpdatePayout:
    def test_update_success(self):
        app, psvc, asvc = _make_app()
        psvc.get_payout_employee.return_value = "100"
        psvc.update_payout.return_value = _payout(amount=7000)
        c = _client(app)

        resp = c.put("/api/payouts/1", json={"amount": 7000})
        assert resp.status_code == 200

    def test_update_not_found_returns_empty(self):
        app, psvc, asvc = _make_app()
        psvc.get_payout_employee.return_value = None
        psvc.update_payout.return_value = None
        c = _client(app)

        resp = c.put("/api/payouts/999", json={"amount": 7000})
        assert resp.status_code == 200
        assert resp.json()["user_id"] == ""


# ===========================================================================
# PUT /api/payouts/{id}/status
# ===========================================================================

class TestSetPayoutStatus:
    def test_set_status(self):
        app, psvc, asvc = _make_app()
        psvc.get_payout_employee.return_value = "100"
        psvc.update_status.return_value = _payout(status="Одобрено")
        c = _client(app)

        resp = c.put("/api/payouts/1/status", json={"status": "Одобрено"})
        assert resp.status_code == 200

    def test_set_status_missing(self):
        app, psvc, asvc = _make_app()
        c = _client(app)

        resp = c.put("/api/payouts/1/status", json={})
        assert resp.status_code == 400

    def test_set_status_not_found(self):
        app, psvc, asvc = _make_app()
        psvc.get_payout_employee.return_value = None
        psvc.update_status.return_value = None
        c = _client(app)

        resp = c.put("/api/payouts/1/status", json={"status": "Одобрено"})
        assert resp.status_code == 404


# ===========================================================================
# POST /api/payouts/{id}/approve, reject, mark_paid
# ===========================================================================

class TestPayoutActions:
    def test_approve(self):
        app, psvc, asvc = _make_app()
        psvc.get_payout_employee.return_value = "100"
        psvc.update_status.return_value = _payout(status="Одобрено")
        c = _client(app)

        resp = c.post("/api/payouts/1/approve")
        assert resp.status_code == 200

    def test_reject(self):
        app, psvc, asvc = _make_app()
        psvc.get_payout_employee.return_value = "100"
        psvc.update_status.return_value = _payout(status="Отклонено")
        c = _client(app)

        resp = c.post("/api/payouts/1/reject")
        assert resp.status_code == 200

    def test_mark_paid(self):
        app, psvc, asvc = _make_app()
        psvc.get_payout_employee.return_value = "100"
        psvc.update_status.return_value = _payout(status="Выплачено")
        c = _client(app)

        resp = c.post("/api/payouts/1/mark_paid")
        assert resp.status_code == 200

    def test_approve_not_found(self):
        app, psvc, asvc = _make_app()
        psvc.get_payout_employee.return_value = None
        psvc.update_status.return_value = None
        c = _client(app)

        resp = c.post("/api/payouts/1/approve")
        assert resp.status_code == 404


# ===========================================================================
# DELETE /api/payouts/{id}
# ===========================================================================

class TestDeletePayout:
    def test_delete(self):
        app, psvc, asvc = _make_app()
        psvc.get_payout_employee.return_value = "100"
        psvc.delete_payout.return_value = True
        c = _client(app)

        resp = c.delete("/api/payouts/1")
        assert resp.status_code == 200
        assert resp.json()["detail"] == "deleted"

    def test_delete_not_found(self):
        app, psvc, asvc = _make_app()
        psvc.get_payout_employee.return_value = None
        psvc.delete_payout.return_value = False
        c = _client(app)

        resp = c.delete("/api/payouts/999")
        assert resp.status_code == 404


# ===========================================================================
# GET /api/payouts/active & /unconfirmed
# ===========================================================================

class TestActivePayouts:
    def test_active(self):
        app, psvc, asvc = _make_app()
        psvc.list_active_payouts.return_value = [_payout()]
        c = _client(app)

        resp = c.get("/api/payouts/active")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_unconfirmed(self):
        app, psvc, asvc = _make_app()
        psvc.list_active_payouts.return_value = [_payout()]
        c = _client(app)

        resp = c.get("/api/payouts/unconfirmed")
        assert resp.status_code == 200


# ===========================================================================
# DELETE /api/payouts/ (bulk)
# ===========================================================================

class TestDeleteMany:
    def test_delete_many(self):
        app, psvc, asvc = _make_app()
        psvc.get_payout_employee.return_value = "100"
        c = _client(app)

        resp = c.delete("/api/payouts/?ids=1,2,3")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ===========================================================================
# GET /api/payouts/control
# ===========================================================================

class TestPayoutsControl:
    def test_control(self):
        app, psvc, asvc = _make_app()
        psvc.list_control.return_value = [
            {"user_id": "100", "name": "Иван", "total": 5000},
        ]
        c = _client(app)

        resp = c.get("/api/payouts/control")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert "user_id" not in data[0]  # user_id stripped
