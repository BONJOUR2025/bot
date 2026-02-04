"""Tests for API salary endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.salary import create_salary_router
from app.api.dependencies import get_current_user
from app.schemas.salary import SalaryRow
from app.services.access_control_service import ResolvedUser


def _resolved(**kw):
    defaults = dict(
        id="admin", login="admin", role_id="owner", role_name="Owner",
        permissions=["*"], bot_buttons=["*"], display_name="Admin",
        allowed_employee_ids=None, allowed_departments=None,
    )
    defaults.update(kw)
    return ResolvedUser(**defaults)


def _salary_row(**kw):
    defaults = dict(
        employee_id="100", name="Иван", month="2025-01",
        shifts_main=0, shifts_extra=0, shifts_total=0,
        salary_fixed=0, salary_repair=0, salary_cosmetics=0,
        salary_shoes=0, salary_accessories=0, salary_keys=0,
        salary_slippers=0, salary_workshop=0, salary_bonus=0,
        salary_total=50000, deduction=0, advance=0,
        final_amount=50000, comment="",
    )
    defaults.update(kw)
    return SalaryRow(**defaults)


def _make_app():
    ssvc = AsyncMock()
    asvc = MagicMock()
    asvc.visible_employee_ids.return_value = None

    app = FastAPI()
    router = create_salary_router(ssvc, asvc)
    app.include_router(router, prefix="/api")
    return app, ssvc, asvc


def _client(app, user=None):
    u = user or _resolved()
    app.dependency_overrides[get_current_user] = lambda: u
    return TestClient(app)


class TestListSalary:
    def test_list(self):
        app, ssvc, asvc = _make_app()
        ssvc.get_salary.return_value = [_salary_row()]
        c = _client(app)
        resp = c.get("/api/salary/")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_with_filters(self):
        app, ssvc, asvc = _make_app()
        ssvc.get_salary.return_value = []
        c = _client(app)
        resp = c.get("/api/salary/?month=2025-01&employee_id=100")
        assert resp.status_code == 200

    def test_list_scoped_user_blocked(self):
        app, ssvc, asvc = _make_app()
        asvc.visible_employee_ids.return_value = {"200"}
        c = _client(app)
        resp = c.get("/api/salary/?employee_id=100")
        assert resp.json() == []


class TestListMonths:
    def test_months(self):
        app, ssvc, asvc = _make_app()
        ssvc.list_months.return_value = ["2025-01", "2025-02"]
        c = _client(app)
        resp = c.get("/api/salary/months")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestSalaryReport:
    def test_report_forbidden_scoped(self):
        app, ssvc, asvc = _make_app()
        asvc.visible_employee_ids.return_value = {"100"}
        c = _client(app)
        resp = c.get("/api/salary/report?month=2025-01")
        assert resp.status_code == 403
