"""Comprehensive tests for PayoutRepository."""

import json
from pathlib import Path

import pytest

from app.data.payout_repository import PayoutRepository, normalize_status
from tests.conftest import make_payout_dict


def _make_repo(tmp_path, data=None):
    p = tmp_path / "payouts.json"
    if data is None:
        data = [make_payout_dict(1), make_payout_dict(2, user_id="200", status="Одобрено")]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return PayoutRepository(file_path=str(p))


class TestNormalizeStatus:
    def test_known_legacy_statuses(self):
        assert normalize_status("Ожидает одобрения") == "Ожидает"
        assert normalize_status("Ожидает выплаты") == "Ожидает"
        assert normalize_status("Утверждено") == "Одобрено"
        assert normalize_status("Подтверждено") == "Одобрено"
        assert normalize_status("Проведено") == "Выплачено"

    def test_already_normalized(self):
        assert normalize_status("Ожидает") == "Ожидает"
        assert normalize_status("Одобрено") == "Одобрено"
        assert normalize_status("Выплачено") == "Выплачено"
        assert normalize_status("Отклонено") == "Отклонено"

    def test_unknown_status_passthrough(self):
        assert normalize_status("Custom") == "Custom"


class TestPayoutRepositoryInit:
    def test_loads_payouts(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert len(repo.load_all()) == 2

    def test_empty_file(self, tmp_path):
        p = tmp_path / "payouts.json"
        p.write_text("[]", encoding="utf-8")
        repo = PayoutRepository(file_path=str(p))
        assert repo.load_all() == []

    def test_missing_file(self, tmp_path):
        repo = PayoutRepository(file_path=str(tmp_path / "nonexistent.json"))
        assert repo.load_all() == []

    def test_normalizes_legacy_statuses(self, tmp_path):
        data = [{"id": 1, "user_id": "1", "status": "В ожидании", "name": "X",
                 "phone": "1", "bank": "S", "amount": 100, "method": "m",
                 "payout_type": "Аванс", "timestamp": "2025-01-01 10:00:00"}]
        p = tmp_path / "payouts.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        repo = PayoutRepository(file_path=str(p))
        assert repo.load_all()[0]["status"] == "Ожидает"

    def test_parses_id_as_int(self, tmp_path):
        data = [{"id": "42", "user_id": "1", "name": "X", "phone": "1", "bank": "S",
                 "amount": 100, "method": "m", "payout_type": "Аванс",
                 "status": "Ожидает", "timestamp": "2025-01-01 10:00:00"}]
        p = tmp_path / "payouts.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        repo = PayoutRepository(file_path=str(p))
        assert repo.load_all()[0]["id"] == 42


class TestPayoutList:
    def test_list_all(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert len(repo.list()) == 2

    def test_filter_by_employee(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.list(employee_id="100")
        assert all(str(r["user_id"]) == "100" for r in result)

    def test_filter_by_status(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.list(status="Одобрено")
        assert len(result) == 1

    def test_filter_by_payout_type(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.list(payout_type="Аванс")
        assert all(r["payout_type"] == "Аванс" for r in result)

    def test_filter_by_method(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.list(method="💳 На карту")
        assert len(result) >= 1

    def test_filter_by_date_range(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.list(from_date="2025-01-01", to_date="2025-12-31")
        assert len(result) == 2

    def test_filter_by_date_excludes(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.list(from_date="2026-01-01")
        assert len(result) == 0

    def test_sorted_by_timestamp_desc(self, tmp_path):
        data = [
            make_payout_dict(1, timestamp="2025-01-10 10:00:00"),
            make_payout_dict(2, timestamp="2025-01-20 10:00:00"),
        ]
        repo = _make_repo(tmp_path, data)
        result = repo.list()
        assert result[0]["timestamp"] >= result[-1]["timestamp"]


class TestPayoutCreate:
    def test_create_assigns_id(self, tmp_path):
        repo = _make_repo(tmp_path, data=[])
        created = repo.create({"user_id": "1", "name": "Test", "amount": 1000})
        assert "id" in created

    def test_create_appends(self, tmp_path):
        repo = _make_repo(tmp_path, data=[])
        repo.create({"user_id": "1", "amount": 100})
        repo.create({"user_id": "2", "amount": 200})
        assert len(repo.load_all()) == 2

    def test_create_avoids_id_collision(self, tmp_path):
        data = [make_payout_dict(1)]
        repo = _make_repo(tmp_path, data)
        created = repo.create({"id": 1, "user_id": "2", "amount": 500})
        assert str(created["id"]) != "1"

    def test_create_persists(self, tmp_path):
        p = tmp_path / "payouts.json"
        p.write_text("[]", encoding="utf-8")
        repo = PayoutRepository(file_path=str(p))
        repo.create({"user_id": "1", "amount": 100})
        raw = json.loads(p.read_text(encoding="utf-8"))
        assert len(raw) == 1


class TestPayoutUpdate:
    def test_update_existing(self, tmp_path):
        repo = _make_repo(tmp_path)
        updated = repo.update("1", {"status": "Одобрено"})
        assert updated is not None
        assert updated["status"] == "Одобрено"

    def test_update_nonexistent_returns_none(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert repo.update("999", {"status": "X"}) is None

    def test_update_skips_none_values(self, tmp_path):
        repo = _make_repo(tmp_path)
        original_name = repo.load_all()[0]["name"]
        repo.update("1", {"name": None, "status": "Одобрено"})
        updated = repo.load_all()[0]
        assert updated["name"] == original_name


class TestPayoutDelete:
    def test_delete_existing(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert repo.delete("1") is True
        assert len(repo.load_all()) == 1

    def test_delete_nonexistent(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert repo.delete("999") is False

    def test_delete_many(self, tmp_path):
        repo = _make_repo(tmp_path)
        repo.delete_many(["1", "2"])
        assert len(repo.load_all()) == 0


class TestPayoutReload:
    def test_reload_picks_up_external_changes(self, tmp_path):
        p = tmp_path / "payouts.json"
        data = [make_payout_dict(1)]
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        repo = PayoutRepository(file_path=str(p))
        assert len(repo.load_all()) == 1
        # externally add a payout
        data.append(make_payout_dict(2))
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        repo.reload()
        assert len(repo.load_all()) == 2
