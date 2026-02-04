"""Comprehensive tests for EmployeeRepository."""

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from app.data.json_storage import JsonStorage
from app.data.employee_repository import EmployeeRepository
from app.core.types import Employee
from app.core.enums import EmployeeStatus
from tests.conftest import make_employee_dict, make_employees_json


def _make_repo(tmp_path, data=None):
    p = tmp_path / "users.json"
    if data is None:
        data = make_employees_json()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    storage = JsonStorage(p)
    return EmployeeRepository(storage=storage)


class TestEmployeeRepositoryInit:
    def test_loads_employees(self, tmp_path):
        repo = _make_repo(tmp_path)
        employees = repo.list_employees(archived=None)
        assert len(employees) == 3

    def test_empty_file_returns_no_employees(self, tmp_path):
        repo = _make_repo(tmp_path, data={})
        assert repo.list_employees(archived=None) == []


class TestListEmployees:
    def test_filter_archived_false(self, tmp_path):
        data = {
            "1": make_employee_dict("1", archived=False),
            "2": make_employee_dict("2", archived=True),
        }
        repo = _make_repo(tmp_path, data)
        active = repo.list_employees(archived=False)
        assert len(active) == 1
        assert active[0].id == "1"

    def test_filter_archived_true(self, tmp_path):
        data = {
            "1": make_employee_dict("1", archived=False),
            "2": make_employee_dict("2", archived=True),
        }
        repo = _make_repo(tmp_path, data)
        archived = repo.list_employees(archived=True)
        assert len(archived) == 1
        assert archived[0].id == "2"

    def test_filter_archived_none_returns_all(self, tmp_path):
        data = {
            "1": make_employee_dict("1", archived=False),
            "2": make_employee_dict("2", archived=True),
        }
        repo = _make_repo(tmp_path, data)
        assert len(repo.list_employees(archived=None)) == 2

    def test_filter_by_status(self, tmp_path):
        repo = _make_repo(tmp_path)
        active = repo.list_employees(archived=None, status="active")
        assert all(e.status == EmployeeStatus.ACTIVE for e in active)

    def test_filter_by_position(self, tmp_path):
        repo = _make_repo(tmp_path)
        admins = repo.list_employees(archived=None, position="Администратор")
        assert len(admins) == 1
        assert admins[0].name == "Мария"

    def test_filter_by_tags(self, tmp_path):
        data = {
            "1": make_employee_dict("1", tags=["vip"]),
            "2": make_employee_dict("2", tags=["regular"]),
        }
        repo = _make_repo(tmp_path, data)
        vip = repo.list_employees(archived=None, tags=["vip"])
        assert len(vip) == 1

    def test_skips_non_dict_entries(self, tmp_path):
        data = {"1": make_employee_dict("1"), "bad": "not a dict"}
        repo = _make_repo(tmp_path, data)
        employees = repo.list_employees(archived=None)
        assert len(employees) == 1


class TestGetEmployee:
    def test_existing_employee(self, tmp_path):
        repo = _make_repo(tmp_path)
        emp = repo.get_employee("100")
        assert emp is not None
        assert emp.name == "Иван"

    def test_missing_employee(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert repo.get_employee("999") is None

    def test_non_dict_entry(self, tmp_path):
        data = {"1": "string_value"}
        repo = _make_repo(tmp_path, data)
        assert repo.get_employee("1") is None


class TestAddEmployee:
    def test_add_new_employee(self, tmp_path):
        repo = _make_repo(tmp_path, data={})
        emp = Employee(
            id="10",
            name="Тест",
            full_name="Тестовый Сотрудник",
            phone="+79999999999",
        )
        repo.add_employee(emp)
        retrieved = repo.get_employee("10")
        assert retrieved is not None
        assert retrieved.name == "Тест"

    def test_add_persists_to_file(self, tmp_path):
        p = tmp_path / "users.json"
        p.write_text("{}", encoding="utf-8")
        storage = JsonStorage(p)
        repo = EmployeeRepository(storage=storage)
        emp = Employee(id="5", name="Новый", full_name="Новый Сотрудник", phone="+7")
        repo.add_employee(emp)
        raw = json.loads(p.read_text(encoding="utf-8"))
        assert "5" in raw


class TestUpdateEmployee:
    def test_update_existing(self, tmp_path):
        repo = _make_repo(tmp_path)
        emp = repo.get_employee("100")
        emp.name = "Обновлённый"
        repo.update_employee(emp)
        updated = repo.get_employee("100")
        assert updated.name == "Обновлённый"

    def test_update_nonexistent_no_error(self, tmp_path):
        repo = _make_repo(tmp_path, data={})
        emp = Employee(id="999", name="X", full_name="X", phone="X")
        repo.update_employee(emp)  # should not raise


class TestDeleteEmployee:
    def test_delete_existing(self, tmp_path):
        repo = _make_repo(tmp_path)
        repo.delete_employee_by_id("100")
        assert repo.get_employee("100") is None

    def test_delete_nonexistent_no_error(self, tmp_path):
        repo = _make_repo(tmp_path)
        repo.delete_employee_by_id("999")  # should not raise


class TestSaveEmployees:
    def test_bulk_save(self, tmp_path):
        repo = _make_repo(tmp_path, data={})
        employees = [
            Employee(id="1", name="A", full_name="AA", phone="1"),
            Employee(id="2", name="B", full_name="BB", phone="2"),
        ]
        repo.save_employees(employees)
        assert repo.get_employee("1") is not None
        assert repo.get_employee("2") is not None


class TestParsers:
    def test_parse_date_iso(self, tmp_path):
        assert EmployeeRepository._parse_date("2000-01-15") == date(2000, 1, 15)

    def test_parse_date_none(self, tmp_path):
        assert EmployeeRepository._parse_date(None) is None

    def test_parse_date_invalid(self, tmp_path):
        assert EmployeeRepository._parse_date("not-a-date") is None

    def test_parse_date_date_object(self, tmp_path):
        d = date(2000, 5, 10)
        assert EmployeeRepository._parse_date(d) == d

    def test_parse_datetime_iso(self, tmp_path):
        result = EmployeeRepository._parse_datetime("2025-01-15T10:30:00")
        assert isinstance(result, datetime)

    def test_parse_datetime_none(self, tmp_path):
        assert EmployeeRepository._parse_datetime(None) is None

    def test_parse_datetime_invalid(self, tmp_path):
        assert EmployeeRepository._parse_datetime("invalid") is None

    def test_birthdate_stored_and_loaded(self, tmp_path):
        data = {"1": make_employee_dict("1", birthdate="1990-05-15")}
        repo = _make_repo(tmp_path, data)
        emp = repo.get_employee("1")
        assert emp.birthdate == date(1990, 5, 15)
