"""Comprehensive tests for API employee endpoints."""

from dataclasses import dataclass
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.employees import create_employee_router
from app.api.dependencies import get_current_user
from app.schemas.employee import EmployeeOut
from app.services.access_control_service import ResolvedUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolved(permissions=None, employee_ids=None, departments=None):
    return ResolvedUser(
        id="admin", login="admin", role_id="owner", role_name="Owner",
        permissions=permissions or ["*"], bot_buttons=["*"],
        display_name="Admin",
        allowed_employee_ids=employee_ids,
        allowed_departments=departments,
    )


def _emp_out(**kw):
    defaults = dict(
        id="100", name="Иван", full_name="Иванов", phone="+7900",
        position="Продавец", is_admin=False, card_number="1234",
        bank="Сбер", work_place="Магазин 1", clothing_size="M",
        birthdate=None, note="", photo_url="", status="active",
        payout_chat_key=None, archived=False, archived_at=None,
        created_at=datetime(2025, 1, 1),
    )
    defaults.update(kw)
    return EmployeeOut(**defaults)


def _make_app():
    employee_svc = AsyncMock()
    employee_svc.service = MagicMock()
    access_svc = MagicMock()

    app = FastAPI()
    router = create_employee_router(employee_svc, access_svc)
    app.include_router(router, prefix="/api")
    return app, employee_svc, access_svc


def _client(app, user=None):
    u = user or _resolved()
    app.dependency_overrides[get_current_user] = lambda: u
    return TestClient(app)


# ===========================================================================
# GET /api/employees/
# ===========================================================================

class TestListEmployees:
    def test_list_all(self):
        app, esvc, asvc = _make_app()
        emp = _emp_out()
        esvc.list_employees.return_value = [emp]
        asvc.is_employee_visible.return_value = True
        c = _client(app)

        resp = c.get("/api/employees/")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["id"] == "100"

    def test_list_filtered_by_access(self):
        app, esvc, asvc = _make_app()
        e1 = _emp_out(id="100")
        e2 = _emp_out(id="200")
        esvc.list_employees.return_value = [e1, e2]
        asvc.is_employee_visible.side_effect = lambda cur, eid, wp: eid == "100"

        c = _client(app)
        resp = c.get("/api/employees/")
        assert len(resp.json()) == 1

    def test_list_archived(self):
        app, esvc, asvc = _make_app()
        esvc.list_employees.return_value = []
        asvc.is_employee_visible.return_value = True
        c = _client(app)

        resp = c.get("/api/employees/?archived=true")
        assert resp.status_code == 200
        esvc.list_employees.assert_called_once_with(archived=True)


# ===========================================================================
# POST /api/employees/
# ===========================================================================

class TestCreateEmployee:
    def test_create_success(self):
        app, esvc, asvc = _make_app()
        asvc.user_employee_scope.return_value = None
        asvc.user_department_scope.return_value = None
        esvc.create_employee.return_value = _emp_out()
        c = _client(app)

        resp = c.post("/api/employees/", json={
            "name": "Иван", "status": "active", "is_admin": False,
        })
        assert resp.status_code == 200

    def test_create_forbidden_scoped_user(self):
        app, esvc, asvc = _make_app()
        asvc.user_employee_scope.return_value = ["100"]
        c = _client(app)

        resp = c.post("/api/employees/", json={
            "name": "Иван", "status": "active", "is_admin": False,
        })
        assert resp.status_code == 403


# ===========================================================================
# PUT /api/employees/{id}
# ===========================================================================

class TestUpdateEmployee:
    def test_update_success(self):
        app, esvc, asvc = _make_app()
        asvc.is_employee_visible.return_value = True
        esvc.service.get_employee.return_value = MagicMock(work_place="M1")
        esvc.update_employee.return_value = _emp_out(name="Мария")
        c = _client(app)

        resp = c.put("/api/employees/100", json={
            "name": "Мария", "status": "active", "is_admin": False,
        })
        assert resp.status_code == 200

    def test_update_forbidden(self):
        app, esvc, asvc = _make_app()
        asvc.is_employee_visible.return_value = False
        esvc.service.get_employee.return_value = MagicMock(work_place="M1")
        c = _client(app)

        resp = c.put("/api/employees/100", json={
            "name": "Мария", "status": "active", "is_admin": False,
        })
        assert resp.status_code == 403


# ===========================================================================
# DELETE /api/employees/{id}
# ===========================================================================

class TestDeleteEmployee:
    def test_delete_success(self):
        app, esvc, asvc = _make_app()
        asvc.is_employee_visible.return_value = True
        esvc.service.get_employee.return_value = MagicMock(work_place="M1")
        esvc.delete_employee.return_value = {"status": "ok"}
        c = _client(app)

        resp = c.delete("/api/employees/100")
        assert resp.status_code == 200

    def test_delete_forbidden(self):
        app, esvc, asvc = _make_app()
        asvc.is_employee_visible.return_value = False
        esvc.service.get_employee.return_value = MagicMock(work_place="M1")
        c = _client(app)

        resp = c.delete("/api/employees/100")
        assert resp.status_code == 403


# ===========================================================================
# POST /api/employees/{id}/archive & /restore
# ===========================================================================

class TestArchiveRestore:
    def test_archive(self):
        app, esvc, asvc = _make_app()
        asvc.is_employee_visible.return_value = True
        esvc.service.get_employee.return_value = MagicMock(work_place="M1")
        esvc.archive_employee.return_value = _emp_out(archived=True)
        c = _client(app)

        resp = c.post("/api/employees/100/archive")
        assert resp.status_code == 200
        assert resp.json()["archived"] is True

    def test_restore(self):
        app, esvc, asvc = _make_app()
        asvc.is_employee_visible.return_value = True
        esvc.service.get_employee.return_value = MagicMock(work_place="M1")
        esvc.restore_employee.return_value = _emp_out(archived=False)
        c = _client(app)

        resp = c.post("/api/employees/100/restore")
        assert resp.status_code == 200
        assert resp.json()["archived"] is False
