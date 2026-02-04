"""Comprehensive tests for AssetRepository."""

import json

import pytest

from app.data.asset_repository import AssetRepository
from tests.conftest import make_asset_dict


def _make_repo(tmp_path, data=None):
    p = tmp_path / "assets.json"
    if data is None:
        data = [
            make_asset_dict(1, issue_date="2025-01-10"),
            make_asset_dict(2, employee_id="200", item_name="Кепка", issue_date="2025-02-01"),
        ]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return AssetRepository(file_path=str(p))


class TestAssetInit:
    def test_loads(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert len(repo.list()) == 2

    def test_empty_file(self, tmp_path):
        p = tmp_path / "assets.json"
        p.write_text("[]", encoding="utf-8")
        repo = AssetRepository(file_path=str(p))
        assert repo.list() == []


class TestAssetList:
    def test_list_all(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert len(repo.list()) == 2

    def test_filter_by_employee(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.list(employee_id="100")
        assert len(result) == 1
        assert result[0]["employee_id"] == "100"

    def test_sorted_by_issue_date(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.list()
        dates = [r.get("issue_date", "") for r in result]
        assert dates == sorted(dates)


class TestAssetCRUD:
    def test_create(self, tmp_path):
        repo = _make_repo(tmp_path, data=[])
        created = repo.create({
            "employee_id": "1", "employee_name": "Test",
            "item_name": "Ботинки", "issue_date": "2025-01-01",
        })
        assert "id" in created
        assert len(repo.list()) == 1

    def test_create_avoids_collision(self, tmp_path):
        data = [make_asset_dict(1)]
        repo = _make_repo(tmp_path, data)
        created = repo.create({"id": 1, "employee_id": "2", "employee_name": "X",
                                "item_name": "Y", "issue_date": "2025-01-01"})
        assert created["id"] != 1

    def test_update_existing(self, tmp_path):
        repo = _make_repo(tmp_path)
        updated = repo.update("1", {"item_name": "Обновлено"})
        assert updated is not None
        assert updated["item_name"] == "Обновлено"

    def test_update_nonexistent(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert repo.update("999", {"item_name": "X"}) is None

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
        p = tmp_path / "assets.json"
        p.write_text("[]", encoding="utf-8")
        repo = AssetRepository(file_path=str(p))
        repo.create({"employee_id": "1", "employee_name": "T", "item_name": "X",
                      "issue_date": "2025-01-01"})
        raw = json.loads(p.read_text(encoding="utf-8"))
        assert len(raw) == 1
