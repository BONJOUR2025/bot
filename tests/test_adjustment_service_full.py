"""Comprehensive tests for AdjustmentService."""

import json
from datetime import datetime
from unittest.mock import patch

import pytest

from app.data.adjustment_repository import AdjustmentRepository
from app.services.adjustment_service import AdjustmentService
from tests.conftest import make_adjustment_dict


def _make_service(tmp_path, data=None):
    p = tmp_path / "adjustments.json"
    if data is None:
        data = [make_adjustment_dict(1), make_adjustment_dict(2, employee_id="200")]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with patch("app.services.adjustment_service.AdjustmentRepository") as MockRepo:
        MockRepo.return_value = AdjustmentRepository(file_path=str(p))
        return AdjustmentService()


class TestAdjustmentServiceList:
    def test_list(self, tmp_path):
        svc = _make_service(tmp_path)
        result = svc.list()
        assert len(result) == 2


class TestAdjustmentServiceCreate:
    def test_create_with_date(self, tmp_path):
        svc = _make_service(tmp_path, data=[])
        result = svc.create({"employee_id": "1", "amount": 500,
                              "date": "2025-01-15", "reason": "test"})
        assert result["date"] == "2025-01-15"

    def test_create_auto_date(self, tmp_path):
        svc = _make_service(tmp_path, data=[])
        result = svc.create({"employee_id": "1", "amount": 500, "reason": "test"})
        assert "date" in result
        assert result["date"] == datetime.today().date().isoformat()

    def test_create_empty_date_gets_today(self, tmp_path):
        svc = _make_service(tmp_path, data=[])
        result = svc.create({"employee_id": "1", "amount": 500, "date": "", "reason": "test"})
        assert result["date"] == datetime.today().date().isoformat()


class TestAdjustmentServiceUpdate:
    def test_update(self, tmp_path):
        svc = _make_service(tmp_path)
        result = svc.update("1", {"reason": "Обновлено"})
        assert result is not None
        assert result["reason"] == "Обновлено"

    def test_update_nonexistent(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.update("999", {"reason": "X"}) is None


class TestAdjustmentServiceDelete:
    def test_delete(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.delete("1")
        assert len(svc.list()) == 1
