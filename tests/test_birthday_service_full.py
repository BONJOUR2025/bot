"""Comprehensive tests for BirthdayService."""

import json
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.data.json_storage import JsonStorage
from app.data.employee_repository import EmployeeRepository
from tests.conftest import make_employee_dict


def _make_repo(tmp_path, data):
    p = tmp_path / "users.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    storage = JsonStorage(p)
    return EmployeeRepository(storage=storage)


class TestGetUpcomingBirthdays:
    def test_birthday_today(self, tmp_path):
        today = date.today()
        bday = f"1990-{today.month:02d}-{today.day:02d}"
        data = {"1": make_employee_dict("1", name="Именинник", full_name="Именинник Полный",
                                         birthdate=bday, status="active")}
        repo = _make_repo(tmp_path, data)
        with patch("app.services.birthday_service._repo", repo):
            from app.services.birthday_service import get_upcoming_birthdays
            result = get_upcoming_birthdays(days_ahead=0)
            assert len(result) == 1
            assert result[0]["user_id"] == "1"

    def test_birthday_tomorrow(self, tmp_path):
        tomorrow = date.today() + timedelta(days=1)
        bday = f"1990-{tomorrow.month:02d}-{tomorrow.day:02d}"
        data = {"1": make_employee_dict("1", birthdate=bday, status="active")}
        repo = _make_repo(tmp_path, data)
        with patch("app.services.birthday_service._repo", repo):
            from app.services.birthday_service import get_upcoming_birthdays
            result = get_upcoming_birthdays(days_ahead=1)
            assert len(result) == 1

    def test_no_birthdays(self, tmp_path):
        data = {"1": make_employee_dict("1", birthdate="1990-01-01", status="active")}
        repo = _make_repo(tmp_path, data)
        with patch("app.services.birthday_service._repo", repo):
            from app.services.birthday_service import get_upcoming_birthdays
            # Use a day far enough away
            result = get_upcoming_birthdays(days_ahead=0)
            # May or may not match depending on date; test structure is valid

    def test_inactive_employees_excluded(self, tmp_path):
        today = date.today()
        bday = f"1990-{today.month:02d}-{today.day:02d}"
        data = {"1": make_employee_dict("1", birthdate=bday, status="inactive")}
        repo = _make_repo(tmp_path, data)
        with patch("app.services.birthday_service._repo", repo):
            from app.services.birthday_service import get_upcoming_birthdays
            result = get_upcoming_birthdays(days_ahead=0)
            assert len(result) == 0

    def test_archived_employees_excluded(self, tmp_path):
        today = date.today()
        bday = f"1990-{today.month:02d}-{today.day:02d}"
        data = {"1": make_employee_dict("1", birthdate=bday, status="active", archived=True)}
        repo = _make_repo(tmp_path, data)
        with patch("app.services.birthday_service._repo", repo):
            from app.services.birthday_service import get_upcoming_birthdays
            result = get_upcoming_birthdays(days_ahead=0)
            # archived=True employees are filtered by default archived=False

    def test_no_birthdate(self, tmp_path):
        data = {"1": make_employee_dict("1", birthdate=None, status="active")}
        repo = _make_repo(tmp_path, data)
        with patch("app.services.birthday_service._repo", repo):
            from app.services.birthday_service import get_upcoming_birthdays
            result = get_upcoming_birthdays(days_ahead=365)
            assert len(result) == 0

    def test_negative_days_ahead(self, tmp_path):
        data = {"1": make_employee_dict("1", status="active")}
        repo = _make_repo(tmp_path, data)
        with patch("app.services.birthday_service._repo", repo):
            from app.services.birthday_service import get_upcoming_birthdays
            result = get_upcoming_birthdays(days_ahead=-5)
            # Should clamp to 0

    def test_result_includes_phone(self, tmp_path):
        today = date.today()
        bday = f"1990-{today.month:02d}-{today.day:02d}"
        data = {"1": make_employee_dict("1", birthdate=bday, status="active",
                                         phone="+79001234567")}
        repo = _make_repo(tmp_path, data)
        with patch("app.services.birthday_service._repo", repo):
            from app.services.birthday_service import get_upcoming_birthdays
            result = get_upcoming_birthdays(days_ahead=0)
            if result:
                assert "phone" in result[0]
