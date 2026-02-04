"""Comprehensive tests for API vacation endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.vacations import create_vacation_router
from app.api.dependencies import get_current_user
from app.schemas.vacation import Vacation
from app.services.access_control_service import ResolvedUser


def _resolved(**kw):
    defaults = dict(
        id="admin", login="admin", role_id="owner", role_name="Owner",
        permissions=["*"], bot_buttons=["*"], display_name="Admin",
        allowed_employee_ids=None, allowed_departments=None,
    )
    defaults.update(kw)
    return ResolvedUser(**defaults)


def _vacation(**kw):
    defaults = dict(
        id=1, employee_id="100", name="Иван",
        start_date="2025-06-01", end_date="2025-06-14",
        type="Отпуск", comment="",
    )
    defaults.update(kw)
    return Vacation(**defaults)


def _make_app():
    vsvc = AsyncMock()
    asvc = MagicMock()
    asvc.visible_employee_ids.return_value = None
    asvc.is_employee_visible.return_value = True

    app = FastAPI()
    router = create_vacation_router(vsvc, asvc)
    app.include_router(router, prefix="/api")
    return app, vsvc, asvc


def _client(app, user=None):
    u = user or _resolved()
    app.dependency_overrides[get_current_user] = lambda: u
    return TestClient(app)


class TestListVacations:
    def test_list(self):
        app, vsvc, asvc = _make_app()
        vsvc.list_vacations.return_value = [_vacation()]
        c = _client(app)
        resp = c.get("/api/vacations/")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_with_filters(self):
        app, vsvc, asvc = _make_app()
        vsvc.list_vacations.return_value = []
        c = _client(app)
        resp = c.get("/api/vacations/?employee_id=100&type=Отпуск")
        assert resp.status_code == 200
        vsvc.list_vacations.assert_called_once_with("100", "Отпуск", None, None)

    def test_list_scoped_blocked(self):
        app, vsvc, asvc = _make_app()
        asvc.visible_employee_ids.return_value = {"200"}
        c = _client(app)
        resp = c.get("/api/vacations/?employee_id=100")
        assert resp.json() == []


class TestCreateVacation:
    def test_create(self):
        app, vsvc, asvc = _make_app()
        vsvc.create_vacation.return_value = _vacation()
        c = _client(app)
        resp = c.post("/api/vacations/", json={
            "employee_id": "100", "name": "Иван",
            "start_date": "2025-06-01", "end_date": "2025-06-14",
            "type": "Отпуск",
        })
        assert resp.status_code == 200

    def test_create_forbidden(self):
        app, vsvc, asvc = _make_app()
        asvc.is_employee_visible.return_value = False
        c = _client(app)
        resp = c.post("/api/vacations/", json={
            "employee_id": "100", "name": "Иван",
            "start_date": "2025-06-01", "end_date": "2025-06-14",
            "type": "Отпуск",
        })
        assert resp.status_code == 403

    def test_create_validation_error(self):
        app, vsvc, asvc = _make_app()
        vsvc.create_vacation.side_effect = ValueError("bad dates")
        c = _client(app)
        resp = c.post("/api/vacations/", json={
            "employee_id": "100", "name": "Иван",
            "start_date": "2025-06-14", "end_date": "2025-06-01",
            "type": "Отпуск",
        })
        assert resp.status_code == 400


class TestUpdateVacation:
    def test_update(self):
        app, vsvc, asvc = _make_app()
        vsvc.get_vacation_employee.return_value = "100"
        vsvc.update_vacation.return_value = _vacation(comment="Обновлено")
        c = _client(app)
        resp = c.put("/api/vacations/1", json={"comment": "Обновлено"})
        assert resp.status_code == 200

    def test_update_not_found(self):
        app, vsvc, asvc = _make_app()
        vsvc.get_vacation_employee.return_value = None
        vsvc.update_vacation.return_value = None
        c = _client(app)
        resp = c.put("/api/vacations/999", json={"comment": "X"})
        assert resp.status_code == 404

    def test_update_validation_error(self):
        app, vsvc, asvc = _make_app()
        vsvc.get_vacation_employee.return_value = "100"
        vsvc.update_vacation.side_effect = ValueError("bad dates")
        c = _client(app)
        resp = c.put("/api/vacations/1", json={"start_date": "2025-06-14"})
        assert resp.status_code == 400


class TestDeleteVacation:
    def test_delete(self):
        app, vsvc, asvc = _make_app()
        vsvc.get_vacation_employee.return_value = "100"
        c = _client(app)
        resp = c.delete("/api/vacations/1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"


class TestActiveVacations:
    def test_active(self):
        app, vsvc, asvc = _make_app()
        vsvc.list_active.return_value = [_vacation()]
        c = _client(app)
        resp = c.get("/api/vacations/active")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestVacationReminders:
    def test_reminders(self):
        app, vsvc, asvc = _make_app()
        vsvc.list_tomorrow.return_value = [_vacation()]
        c = _client(app)
        resp = c.get("/api/vacations/reminders")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
