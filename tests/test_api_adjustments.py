"""Comprehensive tests for API adjustment endpoints."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.adjustments import create_adjustment_router
from app.api.dependencies import get_current_user
from app.services.access_control_service import ResolvedUser


def _resolved():
    return ResolvedUser(
        id="admin", login="admin", role_id="owner", role_name="Owner",
        permissions=["*"], bot_buttons=["*"], display_name="Admin",
        allowed_employee_ids=None, allowed_departments=None,
    )


def _adj_dict(**kw):
    defaults = dict(
        id=1, employee_id="100", employee_name="Иван",
        record_type="Премия", reason="Хорошая работа",
        amount=2000, date="2025-01-15", status="active",
    )
    defaults.update(kw)
    return defaults


def _make_app():
    adj_svc = MagicMock()
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: _resolved()
    router = create_adjustment_router(adj_svc)
    app.include_router(router, prefix="/api")
    return app, adj_svc


class TestListAdjustments:
    def test_list(self):
        app, svc = _make_app()
        svc.list.return_value = [_adj_dict()]
        c = TestClient(app)
        resp = c.get("/api/adjustments/")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestCreateAdjustment:
    def test_create(self):
        app, svc = _make_app()
        svc.create.return_value = _adj_dict()
        c = TestClient(app)
        resp = c.post("/api/adjustments/", json=_adj_dict())
        assert resp.status_code == 200
        assert resp.json()["employee_name"] == "Иван"


class TestUpdateAdjustment:
    def test_update(self):
        app, svc = _make_app()
        svc.update.return_value = _adj_dict(reason="Обновлено")
        c = TestClient(app)
        resp = c.put("/api/adjustments/1", json=_adj_dict(reason="Обновлено"))
        assert resp.status_code == 200
        assert resp.json()["reason"] == "Обновлено"

    def test_update_not_found(self):
        app, svc = _make_app()
        svc.update.return_value = None
        c = TestClient(app)
        resp = c.put("/api/adjustments/999", json=_adj_dict())
        assert resp.status_code == 404


class TestDeleteAdjustment:
    def test_delete(self):
        app, svc = _make_app()
        c = TestClient(app)
        resp = c.delete("/api/adjustments/1")
        assert resp.status_code == 200
        svc.delete.assert_called_once_with("1")
