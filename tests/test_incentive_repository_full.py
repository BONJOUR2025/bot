"""Comprehensive tests for IncentiveRepository."""

import json

import pytest

from app.data.incentive_repository import IncentiveRepository
from tests.conftest import make_incentive_dict


def _make_repo(tmp_path, data=None):
    p = tmp_path / "incentives.json"
    if data is None:
        data = [
            make_incentive_dict(1, type="bonus"),
            make_incentive_dict(2, employee_id="200", type="penalty", date="2025-02-10"),
        ]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return IncentiveRepository(file_path=str(p))


class TestIncentiveInit:
    def test_loads(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert len(repo.list()) == 2

    def test_empty_file(self, tmp_path):
        p = tmp_path / "incentives.json"
        p.write_text("[]", encoding="utf-8")
        repo = IncentiveRepository(file_path=str(p))
        assert repo.list() == []


class TestIncentiveList:
    def test_filter_by_employee(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.list(employee_id="100")
        assert len(result) == 1

    def test_filter_by_type(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.list(typ="penalty")
        assert len(result) == 1

    def test_filter_by_date_range(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.list(date_from="2025-02-01", date_to="2025-02-28")
        assert len(result) == 1

    def test_sorted_by_date_desc(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.list()
        dates = [r.get("date", "") for r in result]
        assert dates == sorted(dates, reverse=True)


class TestIncentiveCreate:
    def test_create(self, tmp_path):
        repo = _make_repo(tmp_path, data=[])
        created = repo.create({
            "employee_id": "1", "name": "Test", "type": "bonus",
            "amount": 500, "reason": "test", "date": "2025-01-01",
            "added_by": "admin",
        })
        assert "id" in created
        assert len(repo.list()) == 1

    def test_create_avoids_collision(self, tmp_path):
        data = [make_incentive_dict(1)]
        repo = _make_repo(tmp_path, data)
        created = repo.create({"id": 1, "employee_id": "2", "type": "penalty",
                                "amount": 100, "reason": "x", "date": "2025-01-01",
                                "added_by": "admin", "name": "X"})
        assert created["id"] != 1


class TestIncentiveUpdate:
    def test_update_unlocked(self, tmp_path):
        repo = _make_repo(tmp_path)
        updated = repo.update("1", {"reason": "Обновлено"})
        assert updated is not None
        assert updated["reason"] == "Обновлено"

    def test_update_locked_returns_none(self, tmp_path):
        data = [make_incentive_dict(1, locked=True)]
        repo = _make_repo(tmp_path, data)
        assert repo.update("1", {"reason": "Попытка"}) is None

    def test_update_nonexistent(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert repo.update("999", {"reason": "X"}) is None


class TestIncentiveDelete:
    def test_delete_unlocked(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert repo.delete("1") is True
        assert len(repo.list()) == 1

    def test_delete_locked_returns_false(self, tmp_path):
        data = [make_incentive_dict(1, locked=True)]
        repo = _make_repo(tmp_path, data)
        assert repo.delete("1") is False
        assert len(repo.list()) == 1

    def test_delete_nonexistent(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert repo.delete("999") is False
