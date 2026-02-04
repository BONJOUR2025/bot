"""Comprehensive tests for the users helper module."""

import json
from datetime import datetime
from unittest.mock import patch

import pytest

from app.data.json_storage import JsonStorage
from app.data.employee_repository import EmployeeRepository
from app.core.types import Employee
from app.core.enums import EmployeeStatus
from tests.conftest import make_employee_dict


def _make_repo(tmp_path, data=None):
    p = tmp_path / "users.json"
    if data is None:
        data = {
            "100": make_employee_dict("100", name="Иван"),
            "200": make_employee_dict("200", name="Мария"),
        }
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    storage = JsonStorage(p)
    return EmployeeRepository(storage=storage)


class TestLoadUsers:
    def test_load_users_list(self, tmp_path):
        repo = _make_repo(tmp_path)
        with patch("app.services.users._repo", repo):
            from app.services.users import load_users
            result = load_users()
            assert len(result) == 2
            assert all("id" in u for u in result)

    def test_load_users_archived_none(self, tmp_path):
        data = {
            "1": make_employee_dict("1", archived=False),
            "2": make_employee_dict("2", archived=True),
        }
        repo = _make_repo(tmp_path, data)
        with patch("app.services.users._repo", repo):
            from app.services.users import load_users
            result = load_users(archived=None)
            assert len(result) == 2

    def test_load_users_map(self, tmp_path):
        repo = _make_repo(tmp_path)
        with patch("app.services.users._repo", repo):
            from app.services.users import load_users_map
            result = load_users_map()
            assert "100" in result
            assert "name" in result["100"]


class TestSaveUsers:
    def test_save_users(self, tmp_path):
        repo = _make_repo(tmp_path, data={})
        with patch("app.services.users._repo", repo):
            from app.services.users import save_users
            users = {
                "10": {"name": "Тест", "full_name": "Тестовый", "phone": "+7"},
            }
            save_users(users)
            emp = repo.get_employee("10")
            assert emp is not None
            assert emp.name == "Тест"


class TestAddUser:
    def test_add_user(self, tmp_path):
        repo = _make_repo(tmp_path, data={})
        with patch("app.services.users._repo", repo):
            from app.services.users import add_user
            add_user("50", {"name": "Новый", "full_name": "Новый Сотрудник", "phone": "+7"})
            emp = repo.get_employee("50")
            assert emp is not None
            assert emp.name == "Новый"


class TestUpdateUser:
    def test_update_user_fields(self, tmp_path):
        repo = _make_repo(tmp_path)
        with patch("app.services.users._repo", repo):
            from app.services.users import update_user
            update_user("100", {"name": "Обновлён"})
            emp = repo.get_employee("100")
            assert emp.name == "Обновлён"

    def test_update_user_archive_sets_timestamp(self, tmp_path):
        repo = _make_repo(tmp_path)
        with patch("app.services.users._repo", repo):
            from app.services.users import update_user, load_users_map
            update_user("100", {"archived": True})
            emp_dict = load_users_map(archived=None).get("100", {})
            assert emp_dict.get("archived") is True
            assert emp_dict.get("archived_at") is not None

    def test_update_user_restore_clears_timestamp(self, tmp_path):
        data = {
            "100": make_employee_dict("100", archived=True,
                                       archived_at=datetime.utcnow().isoformat()),
        }
        repo = _make_repo(tmp_path, data)
        with patch("app.services.users._repo", repo):
            from app.services.users import update_user, load_users_map
            update_user("100", {"archived": False})
            emp_dict = load_users_map(archived=None).get("100", {})
            assert emp_dict.get("archived") is False
            assert emp_dict.get("archived_at") is None

    def test_update_nonexistent_user(self, tmp_path):
        repo = _make_repo(tmp_path)
        with patch("app.services.users._repo", repo):
            from app.services.users import update_user
            update_user("999", {"name": "X"})  # should not raise


class TestDeleteUser:
    def test_delete_user(self, tmp_path):
        repo = _make_repo(tmp_path)
        with patch("app.services.users._repo", repo):
            from app.services.users import delete_user
            delete_user("100")
            assert repo.get_employee("100") is None
