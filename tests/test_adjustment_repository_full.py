"""Comprehensive tests for AdjustmentRepository."""

import json

import pytest

from app.data.adjustment_repository import AdjustmentRepository
from tests.conftest import make_adjustment_dict


def _make_repo(tmp_path, data=None):
    p = tmp_path / "adjustments.json"
    if data is None:
        data = [make_adjustment_dict(1), make_adjustment_dict(2, employee_id="200")]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return AdjustmentRepository(file_path=str(p))


class TestAdjustmentInit:
    def test_loads(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert len(repo.list()) == 2

    def test_empty_file(self, tmp_path):
        p = tmp_path / "adjustments.json"
        p.write_text("[]", encoding="utf-8")
        repo = AdjustmentRepository(file_path=str(p))
        assert repo.list() == []

    def test_missing_file(self, tmp_path):
        repo = AdjustmentRepository(file_path=str(tmp_path / "nope.json"))
        assert repo.list() == []


class TestAdjustmentCRUD:
    def test_create(self, tmp_path):
        repo = _make_repo(tmp_path, data=[])
        created = repo.create({"employee_id": "1", "amount": 500, "reason": "test"})
        assert "id" in created
        assert len(repo.list()) == 1

    def test_create_avoids_id_collision(self, tmp_path):
        data = [make_adjustment_dict(1)]
        repo = _make_repo(tmp_path, data)
        created = repo.create({"id": 1, "employee_id": "2", "amount": 100})
        assert created["id"] != 1

    def test_update_existing(self, tmp_path):
        repo = _make_repo(tmp_path)
        updated = repo.update("1", {"reason": "Обновлено"})
        assert updated is not None
        assert updated["reason"] == "Обновлено"

    def test_update_nonexistent(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert repo.update("999", {"reason": "X"}) is None

    def test_update_skips_none(self, tmp_path):
        repo = _make_repo(tmp_path)
        original = repo.list()[0]["reason"]
        repo.update("1", {"reason": None})
        assert repo.list()[0]["reason"] == original

    def test_delete_existing(self, tmp_path):
        repo = _make_repo(tmp_path)
        repo.delete("1")
        assert len(repo.list()) == 1

    def test_delete_nonexistent(self, tmp_path):
        repo = _make_repo(tmp_path)
        before = len(repo.list())
        repo.delete("999")
        assert len(repo.list()) == before

    def test_persistence(self, tmp_path):
        p = tmp_path / "adjustments.json"
        p.write_text("[]", encoding="utf-8")
        repo = AdjustmentRepository(file_path=str(p))
        repo.create({"employee_id": "1", "amount": 100})
        raw = json.loads(p.read_text(encoding="utf-8"))
        assert len(raw) == 1
