"""Comprehensive tests for IncentiveService."""

import json
import asyncio

import pytest

from app.data.incentive_repository import IncentiveRepository
from app.services.incentive_service import IncentiveService
from app.schemas.incentive import Incentive, IncentiveCreate, IncentiveUpdate
from tests.conftest import make_incentive_dict, run_async


def _make_service(tmp_path, data=None):
    p = tmp_path / "incentives.json"
    if data is None:
        data = [
            make_incentive_dict(1, type="bonus"),
            make_incentive_dict(2, employee_id="200", type="penalty"),
        ]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    repo = IncentiveRepository(file_path=str(p))
    return IncentiveService(repo=repo)


class TestIncentiveServiceList:
    def test_list_all(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            result = await svc.list_incentives()
            assert len(result) == 2
            assert all(isinstance(r, Incentive) for r in result)
        run_async(_run())

    def test_list_filtered(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            result = await svc.list_incentives(typ="bonus")
            assert len(result) == 1
        run_async(_run())

    def test_list_by_employee(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            result = await svc.list_incentives(employee_id="200")
            assert len(result) == 1
        run_async(_run())


class TestIncentiveServiceCreate:
    def test_create(self, tmp_path):
        svc = _make_service(tmp_path, data=[])
        async def _run():
            data = IncentiveCreate(
                employee_id="100", name="Иван", type="bonus",
                amount=1000, reason="За работу", date="2025-01-15",
                added_by="admin",
            )
            result = await svc.create_incentive(data)
            assert isinstance(result, Incentive)
            assert result.amount == 1000
        run_async(_run())


class TestIncentiveServiceUpdate:
    def test_update(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            data = IncentiveUpdate(reason="Обновлено")
            result = await svc.update_incentive("1", data)
            assert result is not None
            assert result.reason == "Обновлено"
        run_async(_run())

    def test_update_locked(self, tmp_path):
        data = [make_incentive_dict(1, locked=True)]
        svc = _make_service(tmp_path, data)
        async def _run():
            update_data = IncentiveUpdate(reason="Попытка")
            result = await svc.update_incentive("1", update_data)
            assert result is None
        run_async(_run())

    def test_update_nonexistent(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            data = IncentiveUpdate(reason="X")
            result = await svc.update_incentive("999", data)
            assert result is None
        run_async(_run())


class TestIncentiveServiceDelete:
    def test_delete(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            result = await svc.delete_incentive("1")
            assert result is True
        run_async(_run())

    def test_delete_locked(self, tmp_path):
        data = [make_incentive_dict(1, locked=True)]
        svc = _make_service(tmp_path, data)
        async def _run():
            result = await svc.delete_incentive("1")
            assert result is False
        run_async(_run())


class TestIncentiveServiceGetEmployee:
    def test_get_employee(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.get_incentive_employee("1") == "100"

    def test_get_employee_nonexistent(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.get_incentive_employee("999") is None
