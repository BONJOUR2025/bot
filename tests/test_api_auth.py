"""Comprehensive tests for API auth endpoints."""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import create_auth_router
from app.api.dependencies import get_current_user
from app.services.access_control_service import ResolvedUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_resolved_user(**kwargs) -> ResolvedUser:
    defaults = dict(
        id="admin", login="admin", role_id="owner", role_name="Owner",
        permissions=["*"], bot_buttons=["*"], display_name="Admin",
        allowed_employee_ids=None, allowed_departments=None,
    )
    defaults.update(kwargs)
    return ResolvedUser(**defaults)


def _make_app(access_service=None) -> tuple[FastAPI, MagicMock]:
    svc = access_service or MagicMock()
    app = FastAPI()
    router = create_auth_router(svc)
    app.include_router(router, prefix="/api")
    return app, svc


def _client_with_user(app, user=None):
    """Return a TestClient that bypasses auth."""
    u = user or _make_resolved_user()
    app.dependency_overrides[get_current_user] = lambda: u
    return TestClient(app)


# ===========================================================================
# POST /api/auth/login
# ===========================================================================

class TestAuthLogin:
    def test_login_success(self):
        app, svc = _make_app()
        resolved = _make_resolved_user()
        svc.authenticate.return_value = resolved
        svc.issue_token.return_value = "tok123"
        client = TestClient(app)

        resp = client.post("/api/auth/login", json={"login": "admin", "password": "pass"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["token"] == "tok123"
        assert body["user"]["login"] == "admin"

    def test_login_sets_cookie(self):
        app, svc = _make_app()
        svc.authenticate.return_value = _make_resolved_user()
        svc.issue_token.return_value = "tok123"
        client = TestClient(app)

        resp = client.post("/api/auth/login", json={"login": "admin", "password": "pass"})
        assert "access_token" in resp.cookies

    def test_login_invalid_credentials(self):
        app, svc = _make_app()
        svc.authenticate.return_value = None
        client = TestClient(app)

        resp = client.post("/api/auth/login", json={"login": "bad", "password": "bad"})
        assert resp.status_code == 401

    def test_login_missing_fields(self):
        app, svc = _make_app()
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"login": "admin"})
        assert resp.status_code == 422


# ===========================================================================
# GET /api/auth/me
# ===========================================================================

class TestAuthMe:
    def test_me_returns_user(self):
        app, svc = _make_app()
        user = _make_resolved_user()
        client = _client_with_user(app, user)

        resp = client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["id"] == "admin"


# ===========================================================================
# POST /api/auth/logout
# ===========================================================================

class TestAuthLogout:
    def test_logout(self):
        app, svc = _make_app()
        client = TestClient(app)
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ===========================================================================
# GET /api/auth/access
# ===========================================================================

class TestAuthAccess:
    def test_access_config(self):
        app, svc = _make_app()
        svc.list_users.return_value = []
        svc.list_roles.return_value = []
        svc.available_permissions.return_value = [
            {"id": "dashboard", "label": "Дашборд"},
        ]
        svc.available_bot_buttons.return_value = [
            {"id": "btn1", "label": "Button 1", "scope": "user", "text": "Btn1"},
        ]
        svc.available_employees.return_value = []
        svc.available_departments.return_value = []

        user = _make_resolved_user()
        client = _client_with_user(app, user)

        resp = client.get("/api/auth/access")
        assert resp.status_code == 200
        body = resp.json()
        assert "users" in body
        assert "roles" in body

    def test_access_forbidden_without_permission(self):
        app, svc = _make_app()
        user = _make_resolved_user(permissions=[])
        client = _client_with_user(app, user)

        resp = client.get("/api/auth/access")
        assert resp.status_code == 403


# ===========================================================================
# ROLES CRUD
# ===========================================================================

class TestAuthRoles:
    def test_create_role(self):
        app, svc = _make_app()
        svc.create_role.return_value = {"id": "mgr", "name": "Manager",
                                         "permissions": [], "bot_buttons": []}
        client = _client_with_user(app)

        resp = client.post("/api/auth/roles", json={"name": "Manager"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Manager"

    def test_create_role_duplicate(self):
        app, svc = _make_app()
        svc.create_role.side_effect = ValueError("role_exists")
        client = _client_with_user(app)

        resp = client.post("/api/auth/roles", json={"name": "Manager"})
        assert resp.status_code == 400

    def test_update_role(self):
        app, svc = _make_app()
        svc.update_role.return_value = {"id": "mgr", "name": "Manager 2",
                                         "permissions": [], "bot_buttons": []}
        client = _client_with_user(app)

        resp = client.patch("/api/auth/roles/mgr", json={"name": "Manager 2"})
        assert resp.status_code == 200

    def test_update_role_not_found(self):
        app, svc = _make_app()
        svc.update_role.side_effect = ValueError("role_not_found")
        client = _client_with_user(app)

        resp = client.patch("/api/auth/roles/xxx", json={"name": "X"})
        assert resp.status_code == 404

    def test_delete_role(self):
        app, svc = _make_app()
        client = _client_with_user(app)
        resp = client.delete("/api/auth/roles/mgr")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_role_in_use(self):
        app, svc = _make_app()
        svc.delete_role.side_effect = ValueError("role_in_use")
        client = _client_with_user(app)

        resp = client.delete("/api/auth/roles/owner")
        assert resp.status_code == 400


# ===========================================================================
# USERS CRUD
# ===========================================================================

class TestAuthUsers:
    def test_create_user(self):
        app, svc = _make_app()
        svc.create_user.return_value = {"id": "u1", "login": "john", "role_id": "owner",
                                         "permissions": None, "bot_buttons": None,
                                         "allowed_employee_ids": None,
                                         "allowed_departments": None}
        resolved = _make_resolved_user(id="u1", login="john")
        svc.resolve_user.return_value = resolved
        svc.button_labels.return_value = []
        svc._employee_names.return_value = []

        client = _client_with_user(app)
        resp = client.post("/api/auth/users", json={"login": "john", "password": "pass"})
        assert resp.status_code == 200
        assert resp.json()["login"] == "john"

    def test_create_user_duplicate_login(self):
        app, svc = _make_app()
        svc.create_user.side_effect = ValueError("login_exists")
        client = _client_with_user(app)

        resp = client.post("/api/auth/users", json={"login": "admin", "password": "pass"})
        assert resp.status_code == 400

    def test_update_user(self):
        app, svc = _make_app()
        svc.update_user.return_value = {"id": "u1", "login": "john", "role_id": "owner",
                                         "permissions": None, "bot_buttons": None,
                                         "allowed_employee_ids": None,
                                         "allowed_departments": None}
        resolved = _make_resolved_user(id="u1", login="john")
        svc.resolve_user.return_value = resolved
        svc.button_labels.return_value = []
        svc._employee_names.return_value = []

        client = _client_with_user(app)
        resp = client.patch("/api/auth/users/u1", json={"login": "john2"})
        assert resp.status_code == 200

    def test_delete_user(self):
        app, svc = _make_app()
        client = _client_with_user(app)
        resp = client.delete("/api/auth/users/u1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
