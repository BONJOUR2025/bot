"""Comprehensive tests for API asset endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.assets import create_asset_router
from app.api.dependencies import get_current_user
from app.schemas.asset import Asset
from app.services.access_control_service import ResolvedUser


def _resolved(**kw):
    defaults = dict(
        id="admin", login="admin", role_id="owner", role_name="Owner",
        permissions=["*"], bot_buttons=["*"], display_name="Admin",
        allowed_employee_ids=None, allowed_departments=None,
    )
    defaults.update(kw)
    return ResolvedUser(**defaults)


def _asset(**kw):
    defaults = dict(
        id=1, employee_id="100", employee_name="Иван",
        position="Продавец", item_name="Футболка", size="M",
        quantity=1, issue_date="2025-01-10",
        return_date=None, service_life=None,
    )
    defaults.update(kw)
    return Asset(**defaults)


def _make_app():
    asvc_asset = AsyncMock()
    asvc_access = MagicMock()
    asvc_access.visible_employee_ids.return_value = None
    asvc_access.is_employee_visible.return_value = True

    app = FastAPI()
    router = create_asset_router(asvc_asset, asvc_access)
    app.include_router(router, prefix="/api")
    return app, asvc_asset, asvc_access


def _client(app, user=None):
    u = user or _resolved()
    app.dependency_overrides[get_current_user] = lambda: u
    return TestClient(app)


class TestListAssets:
    def test_list(self):
        app, asvc, acc = _make_app()
        asvc.list_assets.return_value = [_asset()]
        c = _client(app)
        resp = c.get("/api/assets/")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_by_employee(self):
        app, asvc, acc = _make_app()
        asvc.list_assets.return_value = [_asset()]
        c = _client(app)
        resp = c.get("/api/assets/?employee_id=100")
        assert resp.status_code == 200

    def test_list_scoped_blocked(self):
        app, asvc, acc = _make_app()
        acc.visible_employee_ids.return_value = {"200"}
        c = _client(app)
        resp = c.get("/api/assets/?employee_id=100")
        assert resp.json() == []


class TestCreateAsset:
    def test_create(self):
        app, asvc, acc = _make_app()
        asvc.create_asset.return_value = _asset()
        c = _client(app)
        resp = c.post("/api/assets/", json={
            "employee_id": "100", "employee_name": "Иван",
            "item_name": "Футболка", "quantity": 1,
            "issue_date": "2025-01-10",
        })
        assert resp.status_code == 200

    def test_create_forbidden(self):
        app, asvc, acc = _make_app()
        acc.is_employee_visible.return_value = False
        c = _client(app)
        resp = c.post("/api/assets/", json={
            "employee_id": "100", "employee_name": "Иван",
            "item_name": "Футболка", "quantity": 1,
            "issue_date": "2025-01-10",
        })
        assert resp.status_code == 403


class TestUpdateAsset:
    def test_update(self):
        app, asvc, acc = _make_app()
        asvc.get_asset_employee.return_value = "100"
        asvc.update_asset.return_value = _asset(item_name="Шорты")
        c = _client(app)
        resp = c.put("/api/assets/1", json={"item_name": "Шорты"})
        assert resp.status_code == 200

    def test_update_not_found(self):
        app, asvc, acc = _make_app()
        asvc.get_asset_employee.return_value = None
        asvc.update_asset.return_value = None
        c = _client(app)
        resp = c.put("/api/assets/999", json={"item_name": "X"})
        assert resp.status_code == 404


class TestDeleteAsset:
    def test_delete(self):
        app, asvc, acc = _make_app()
        asvc.get_asset_employee.return_value = "100"
        c = _client(app)
        resp = c.delete("/api/assets/1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
