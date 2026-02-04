"""Comprehensive tests for AssetService."""

import json
import asyncio

import pytest

from app.data.asset_repository import AssetRepository
from app.services.asset_service import AssetService
from app.schemas.asset import Asset, AssetCreate, AssetUpdate
from tests.conftest import make_asset_dict, run_async


def _make_service(tmp_path, data=None):
    p = tmp_path / "assets.json"
    if data is None:
        data = [
            make_asset_dict(1),
            make_asset_dict(2, employee_id="200", item_name="Кепка"),
        ]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    repo = AssetRepository(file_path=str(p))
    return AssetService(repo=repo)


class TestAssetServiceList:
    def test_list_all(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            result = await svc.list_assets()
            assert len(result) == 2
            assert all(isinstance(r, Asset) for r in result)
        run_async(_run())

    def test_list_by_employee(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            result = await svc.list_assets(employee_id="100")
            assert len(result) == 1
        run_async(_run())


class TestAssetServiceCreate:
    def test_create(self, tmp_path):
        svc = _make_service(tmp_path, data=[])
        async def _run():
            data = AssetCreate(
                employee_id="100", employee_name="Иван",
                item_name="Ботинки", issue_date="2025-01-01",
            )
            result = await svc.create_asset(data)
            assert isinstance(result, Asset)
            assert result.item_name == "Ботинки"
        run_async(_run())


class TestAssetServiceUpdate:
    def test_update(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            data = AssetUpdate(item_name="Обновлено")
            result = await svc.update_asset("1", data)
            assert result is not None
            assert result.item_name == "Обновлено"
        run_async(_run())

    def test_update_nonexistent(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            data = AssetUpdate(item_name="X")
            result = await svc.update_asset("999", data)
            assert result is None
        run_async(_run())


class TestAssetServiceDelete:
    def test_delete(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            await svc.delete_asset("1")
            result = await svc.list_assets()
            assert len(result) == 1
        run_async(_run())


class TestAssetServiceGetEmployee:
    def test_get_employee(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.get_asset_employee("1") == "100"

    def test_get_employee_nonexistent(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.get_asset_employee("999") is None
