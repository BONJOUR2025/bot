"""Comprehensive tests for VacationRepository."""

import json
from datetime import date, timedelta

import pytest

from app.data.vacation_repository import VacationRepository
from tests.conftest import make_vacation_dict


def _make_repo(tmp_path, data=None):
    p = tmp_path / "vacations.json"
    if data is None:
        data = [make_vacation_dict(1), make_vacation_dict(2, employee_id="200", name="Мария")]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return VacationRepository(file_path=str(p))


class TestVacationRepositoryInit:
    def test_loads_vacations(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert len(repo.list()) == 2

    def test_empty_file(self, tmp_path):
        p = tmp_path / "vacations.json"
        p.write_text("[]", encoding="utf-8")
        repo = VacationRepository(file_path=str(p))
        assert repo.list() == []

    def test_missing_file(self, tmp_path):
        repo = VacationRepository(file_path=str(tmp_path / "nonexistent.json"))
        assert repo.list() == []


class TestVacationList:
    def test_list_all(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert len(repo.list()) == 2

    def test_filter_by_employee(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.list(employee_id="100")
        assert len(result) == 1

    def test_filter_by_type(self, tmp_path):
        data = [
            make_vacation_dict(1, type="Отпуск"),
            make_vacation_dict(2, type="Больничный"),
        ]
        repo = _make_repo(tmp_path, data)
        result = repo.list(vac_type="Больничный")
        assert len(result) == 1

    def test_filter_by_date_range(self, tmp_path):
        data = [
            make_vacation_dict(1, start_date="2025-01-01", end_date="2025-01-14"),
            make_vacation_dict(2, start_date="2025-06-01", end_date="2025-06-14"),
        ]
        repo = _make_repo(tmp_path, data)
        result = repo.list(date_from="2025-05-01", date_to="2025-12-31")
        assert len(result) == 1

    def test_sorted_by_start_date(self, tmp_path):
        data = [
            make_vacation_dict(2, start_date="2025-06-01", end_date="2025-06-14"),
            make_vacation_dict(1, start_date="2025-01-01", end_date="2025-01-14"),
        ]
        repo = _make_repo(tmp_path, data)
        result = repo.list()
        assert result[0]["start_date"] <= result[1]["start_date"]


class TestVacationCreate:
    def test_create_assigns_id(self, tmp_path):
        repo = _make_repo(tmp_path, data=[])
        created = repo.create({
            "employee_id": "1", "name": "Test",
            "start_date": "2025-01-01", "end_date": "2025-01-14",
            "type": "Отпуск",
        })
        assert "id" in created

    def test_create_appends(self, tmp_path):
        repo = _make_repo(tmp_path, data=[])
        repo.create({"employee_id": "1", "name": "A", "start_date": "2025-01-01",
                      "end_date": "2025-01-07", "type": "Отпуск"})
        repo.create({"employee_id": "2", "name": "B", "start_date": "2025-02-01",
                      "end_date": "2025-02-07", "type": "Больничный"})
        assert len(repo.list()) == 2

    def test_create_avoids_id_collision(self, tmp_path):
        data = [make_vacation_dict(1)]
        repo = _make_repo(tmp_path, data)
        created = repo.create({"id": 1, "employee_id": "2", "name": "X",
                                "start_date": "2025-03-01", "end_date": "2025-03-07",
                                "type": "Отпуск"})
        assert created["id"] != 1


class TestVacationUpdate:
    def test_update_existing(self, tmp_path):
        repo = _make_repo(tmp_path)
        updated = repo.update("1", {"comment": "Обновлено"})
        assert updated is not None
        assert updated["comment"] == "Обновлено"

    def test_update_nonexistent(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert repo.update("999", {"comment": "X"}) is None


class TestVacationDelete:
    def test_delete_existing(self, tmp_path):
        repo = _make_repo(tmp_path)
        repo.delete("1")
        assert len(repo.list()) == 1

    def test_delete_nonexistent(self, tmp_path):
        repo = _make_repo(tmp_path)
        before = len(repo.list())
        repo.delete("999")
        assert len(repo.list()) == before


class TestVacationActive:
    def test_list_active(self, tmp_path):
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        data = [
            make_vacation_dict(1, start_date=yesterday, end_date=tomorrow),
            make_vacation_dict(2, start_date="2020-01-01", end_date="2020-01-14"),
        ]
        repo = _make_repo(tmp_path, data)
        active = repo.list_active()
        assert len(active) == 1
        assert active[0]["id"] == 1

    def test_list_tomorrow(self, tmp_path):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        data = [
            make_vacation_dict(1, start_date=tomorrow, end_date="2025-12-31"),
            make_vacation_dict(2, start_date="2025-01-01", end_date="2025-01-14"),
        ]
        repo = _make_repo(tmp_path, data)
        result = repo.list_tomorrow()
        assert len(result) == 1
