"""Comprehensive tests for VacationService."""

import json
import asyncio
from datetime import date, timedelta

import pytest

from app.data.vacation_repository import VacationRepository
from app.services.vacation_service import VacationService
from app.schemas.vacation import Vacation, VacationCreate, VacationUpdate
from tests.conftest import make_vacation_dict, run_async


def _make_service(tmp_path, data=None):
    p = tmp_path / "vacations.json"
    if data is None:
        data = [make_vacation_dict(1), make_vacation_dict(2, employee_id="200")]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    repo = VacationRepository(file_path=str(p))
    return VacationService(repo=repo)


class TestVacationServiceList:
    def test_list_all(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            result = await svc.list_vacations()
            assert len(result) == 2
            assert all(isinstance(r, Vacation) for r in result)
        run_async(_run())

    def test_list_filtered_by_employee(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            result = await svc.list_vacations(employee_id="100")
            assert len(result) == 1
        run_async(_run())

    def test_list_filtered_by_type(self, tmp_path):
        data = [
            make_vacation_dict(1, type="Отпуск"),
            make_vacation_dict(2, type="Больничный"),
        ]
        svc = _make_service(tmp_path, data)
        async def _run():
            result = await svc.list_vacations(vac_type="Больничный")
            assert len(result) == 1
        run_async(_run())


class TestVacationServiceCreate:
    def test_create_vacation(self, tmp_path):
        svc = _make_service(tmp_path, data=[])
        async def _run():
            data = VacationCreate(
                employee_id="100", name="Иван",
                start_date="2025-06-01", end_date="2025-06-14",
                type="Отпуск",
            )
            result = await svc.create_vacation(data)
            assert isinstance(result, Vacation)
            assert result.employee_id == "100"
        run_async(_run())

    def test_create_invalid_dates_raises(self, tmp_path):
        svc = _make_service(tmp_path, data=[])
        async def _run():
            data = VacationCreate(
                employee_id="100", name="Иван",
                start_date="2025-06-14", end_date="2025-06-01",
                type="Отпуск",
            )
            with pytest.raises(ValueError, match="start_date must be before end_date"):
                await svc.create_vacation(data)
        run_async(_run())


class TestVacationServiceUpdate:
    def test_update_vacation(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            data = VacationUpdate(comment="Обновлено")
            result = await svc.update_vacation("1", data)
            assert result is not None
            assert result.comment == "Обновлено"
        run_async(_run())

    def test_update_nonexistent(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            data = VacationUpdate(comment="X")
            result = await svc.update_vacation("999", data)
            assert result is None
        run_async(_run())

    def test_update_invalid_dates_raises(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            data = VacationUpdate(start_date="2025-12-31", end_date="2025-01-01")
            with pytest.raises(ValueError):
                await svc.update_vacation("1", data)
        run_async(_run())


class TestVacationServiceDelete:
    def test_delete_vacation(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            await svc.delete_vacation("1")
            result = await svc.list_vacations()
            assert len(result) == 1
        run_async(_run())


class TestVacationServiceActive:
    def test_list_active(self, tmp_path):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        data = [
            make_vacation_dict(1, start_date=yesterday, end_date=tomorrow),
            make_vacation_dict(2, start_date="2020-01-01", end_date="2020-01-14"),
        ]
        svc = _make_service(tmp_path, data)
        async def _run():
            result = await svc.list_active()
            assert len(result) == 1
        run_async(_run())

    def test_list_tomorrow(self, tmp_path):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        data = [make_vacation_dict(1, start_date=tomorrow, end_date="2025-12-31")]
        svc = _make_service(tmp_path, data)
        async def _run():
            result = await svc.list_tomorrow()
            assert len(result) == 1
        run_async(_run())


class TestVacationServiceGetEmployee:
    def test_get_employee(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.get_vacation_employee("1") == "100"

    def test_get_employee_nonexistent(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.get_vacation_employee("999") is None


class TestValidateDates:
    def test_valid_dates(self):
        VacationService._validate_dates("2025-01-01", "2025-01-14")

    def test_invalid_dates(self):
        with pytest.raises(ValueError):
            VacationService._validate_dates("2025-01-14", "2025-01-01")

    def test_empty_dates(self):
        VacationService._validate_dates("", "")
        VacationService._validate_dates(None, None)
