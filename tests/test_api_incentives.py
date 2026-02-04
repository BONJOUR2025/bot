"""Comprehensive tests for API incentive endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.incentives import create_incentive_router
from app.api.dependencies import get_current_user
from app.schemas.incentive import Incentive
from app.services.access_control_service import ResolvedUser


def _resolved(**kw):
    defaults = dict(
        id="admin", login="admin", role_id="owner", role_name="Owner",
        permissions=["*"], bot_buttons=["*"], display_name="Admin",
        allowed_employee_ids=None, allowed_departments=None,
    )
    defaults.update(kw)
    return ResolvedUser(**defaults)


def _incentive(**kw):
    defaults = dict(
        id=1, employee_id="100", name="Иван", type="bonus",
        amount=1000, reason="Хорошая работа", date="2025-01-15",
        added_by="admin", locked=False,
    )
    defaults.update(kw)
    return Incentive(**defaults)


def _make_app():
    isvc = AsyncMock()
    asvc = MagicMock()
    asvc.visible_employee_ids.return_value = None
    asvc.is_employee_visible.return_value = True

    app = FastAPI()
    router = create_incentive_router(isvc, asvc)
    app.include_router(router, prefix="/api")
    return app, isvc, asvc


def _client(app, user=None):
    u = user or _resolved()
    app.dependency_overrides[get_current_user] = lambda: u
    return TestClient(app)


class TestListIncentives:
    def test_list(self):
        app, isvc, asvc = _make_app()
        isvc.list_incentives.return_value = [_incentive()]
        c = _client(app)
        resp = c.get("/api/incentives/")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_filtered_by_type(self):
        app, isvc, asvc = _make_app()
        isvc.list_incentives.return_value = []
        c = _client(app)
        resp = c.get("/api/incentives/?type=bonus&employee_id=100")
        assert resp.status_code == 200

    def test_list_scoped_blocked(self):
        app, isvc, asvc = _make_app()
        asvc.visible_employee_ids.return_value = {"200"}
        c = _client(app)
        resp = c.get("/api/incentives/?employee_id=100")
        assert resp.json() == []


class TestCreateIncentive:
    def test_create(self):
        app, isvc, asvc = _make_app()
        isvc.create_incentive.return_value = _incentive()
        c = _client(app)
        resp = c.post("/api/incentives/", json={
            "employee_id": "100", "name": "Иван", "type": "bonus",
            "amount": 1000, "reason": "Бонус", "date": "2025-01-15",
            "added_by": "admin",
        })
        assert resp.status_code == 200

    def test_create_forbidden(self):
        app, isvc, asvc = _make_app()
        asvc.is_employee_visible.return_value = False
        c = _client(app)
        resp = c.post("/api/incentives/", json={
            "employee_id": "100", "name": "Иван", "type": "bonus",
            "amount": 1000, "reason": "Бонус", "date": "2025-01-15",
            "added_by": "admin",
        })
        assert resp.status_code == 403


class TestUpdateIncentive:
    def test_update(self):
        app, isvc, asvc = _make_app()
        isvc.get_incentive_employee.return_value = "100"
        isvc.update_incentive.return_value = _incentive(reason="Обновлено")
        c = _client(app)
        resp = c.patch("/api/incentives/1", json={"reason": "Обновлено"})
        assert resp.status_code == 200

    def test_update_not_found_or_locked(self):
        app, isvc, asvc = _make_app()
        isvc.get_incentive_employee.return_value = None
        isvc.update_incentive.return_value = None
        c = _client(app)
        resp = c.patch("/api/incentives/999", json={"reason": "X"})
        assert resp.status_code == 404


class TestDeleteIncentive:
    def test_delete(self):
        app, isvc, asvc = _make_app()
        isvc.get_incentive_employee.return_value = "100"
        isvc.delete_incentive.return_value = True
        c = _client(app)
        resp = c.delete("/api/incentives/1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_locked(self):
        app, isvc, asvc = _make_app()
        isvc.get_incentive_employee.return_value = "100"
        isvc.delete_incentive.return_value = False
        c = _client(app)
        resp = c.delete("/api/incentives/1")
        assert resp.status_code == 404
