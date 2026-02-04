"""Tests for API config, dictionary, birthday, and schedule endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.config import create_config_router
from app.api.dictionary import create_dictionary_router
from app.api.birthdays import create_birthday_router
from app.api.schedule import create_schedule_router
from app.api.dependencies import get_current_user
from app.services.access_control_service import ResolvedUser


def _resolved():
    return ResolvedUser(
        id="admin", login="admin", role_id="owner", role_name="Owner",
        permissions=["*"], bot_buttons=["*"], display_name="Admin",
        allowed_employee_ids=None, allowed_departments=None,
    )


# ===========================================================================
# CONFIG
# ===========================================================================

class TestConfigAPI:
    def _make(self):
        svc = MagicMock()
        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: _resolved()
        app.include_router(create_config_router(svc), prefix="/api")
        return TestClient(app), svc

    def test_get_config(self):
        c, svc = self._make()
        svc.load.return_value = {"key": "value"}
        resp = c.get("/api/config/")
        assert resp.status_code == 200
        assert resp.json()["key"] == "value"

    def test_post_config(self):
        c, svc = self._make()
        svc.save.return_value = {"replaced": True}
        resp = c.post("/api/config/", json={"replaced": True})
        assert resp.status_code == 200

    def test_patch_config(self):
        c, svc = self._make()
        svc.patch.return_value = {"merged": True}
        resp = c.patch("/api/config/", json={"merged": True})
        assert resp.status_code == 200


# ===========================================================================
# DICTIONARY
# ===========================================================================

class TestDictionaryAPI:
    def _make(self):
        svc = MagicMock()
        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: _resolved()
        app.include_router(create_dictionary_router(svc), prefix="/api")
        return TestClient(app), svc

    def test_get_dictionary(self):
        c, svc = self._make()
        svc.load.return_value = {"positions": ["A", "B"]}
        resp = c.get("/api/dictionary/")
        assert resp.status_code == 200
        assert "positions" in resp.json()

    def test_patch_dictionary(self):
        c, svc = self._make()
        svc.patch.return_value = {"positions": ["A", "B", "C"]}
        resp = c.patch("/api/dictionary/", json={"positions": ["A", "B", "C"]})
        assert resp.status_code == 200


# ===========================================================================
# BIRTHDAYS
# ===========================================================================

class TestBirthdaysAPI:
    def _make(self):
        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: _resolved()
        app.include_router(create_birthday_router(), prefix="/api")
        return TestClient(app)

    @patch("app.api.birthdays.get_upcoming_birthdays")
    def test_list_birthdays(self, mock_fn):
        mock_fn.return_value = [
            {"user_id": "100", "full_name": "Иван", "birthdate": "1990-06-15", "phone": None},
        ]
        c = self._make()
        resp = c.get("/api/birthdays/?days=30")
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(30)

    @patch("app.api.birthdays.get_upcoming_birthdays")
    def test_list_birthdays_default_days(self, mock_fn):
        mock_fn.return_value = []
        c = self._make()
        resp = c.get("/api/birthdays/")
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(1)


# ===========================================================================
# SCHEDULE
# ===========================================================================

class TestScheduleAPI:
    def _make(self):
        svc = AsyncMock()
        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: _resolved()
        app.include_router(create_schedule_router(svc), prefix="/api")
        return TestClient(app), svc

    def test_schedule_by_day(self):
        c, svc = self._make()
        svc.get_schedule_by_day.return_value = [
            {"point": "Точка 1", "short": "Т1", "employee": "Иван"},
        ]
        resp = c.get("/api/schedule/by_day?date=2025-01-15")
        assert resp.status_code == 200
        svc.get_schedule_by_day.assert_called_once_with("2025-01-15")

    def test_schedule_requires_date(self):
        c, svc = self._make()
        resp = c.get("/api/schedule/by_day")
        assert resp.status_code == 422
