"""Comprehensive tests for EmployeeService and EmployeeAPIService."""

import json
import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from app.data.json_storage import JsonStorage
from app.data.employee_repository import EmployeeRepository
from app.core.types import Employee
from app.core.enums import EmployeeStatus
from app.services.employee_service import EmployeeService, EmployeeAPIService
from app.schemas.employee import EmployeeCreate, EmployeeUpdate
from tests.conftest import make_employee_dict, make_employees_json, run_async


def _make_service(tmp_path, data=None):
    p = tmp_path / "users.json"
    if data is None:
        data = make_employees_json()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    storage = JsonStorage(p)
    repo = EmployeeRepository(storage=storage)
    return EmployeeService(repo=repo)


# ---------------------------------------------------------------------------
# EmployeeService
# ---------------------------------------------------------------------------

class TestEmployeeServiceList:
    def test_list_active(self, tmp_path):
        svc = _make_service(tmp_path)
        active = svc.list_employees(archived=False)
        assert all(not e.archived for e in active)

    def test_list_archived(self, tmp_path):
        data = {
            "1": make_employee_dict("1", archived=True),
            "2": make_employee_dict("2", archived=False),
        }
        svc = _make_service(tmp_path, data)
        archived = svc.list_employees(archived=True)
        assert len(archived) == 1

    def test_list_all(self, tmp_path):
        svc = _make_service(tmp_path)
        all_emps = svc.list_employees(archived=None)
        assert len(all_emps) == 3


class TestEmployeeServiceAdd:
    def test_add_employee(self, tmp_path):
        svc = _make_service(tmp_path, data={})
        emp = Employee(id="10", name="Тест", full_name="Тест Тестов", phone="+7")
        result = svc.add_employee(emp)
        assert result.id == "10"
        assert svc.get_employee("10") is not None

    def test_add_auto_id(self, tmp_path):
        svc = _make_service(tmp_path, data={})
        emp = Employee(id="", name="Авто", full_name="Авто Айди", phone="+7")
        result = svc.add_employee(emp)
        assert result.id != ""

    def test_add_duplicate_raises(self, tmp_path):
        svc = _make_service(tmp_path)
        emp = Employee(id="100", name="Дубль", full_name="Д", phone="+7")
        with pytest.raises(ValueError, match="employee_exists"):
            svc.add_employee(emp)

    def test_add_normalizes_status(self, tmp_path):
        svc = _make_service(tmp_path, data={})
        emp = Employee(id="5", name="N", full_name="N", phone="+7", status="active")
        result = svc.add_employee(emp)
        assert result.status == EmployeeStatus.ACTIVE


class TestEmployeeServiceUpdate:
    def test_update_employee(self, tmp_path):
        svc = _make_service(tmp_path)
        updated = svc.update_employee("100", name="НовоеИмя")
        assert updated is not None
        assert updated.name == "НовоеИмя"

    def test_update_nonexistent(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.update_employee("999", name="X") is None

    def test_update_status_string(self, tmp_path):
        svc = _make_service(tmp_path)
        updated = svc.update_employee("100", status="inactive")
        assert updated.status == EmployeeStatus.INACTIVE

    def test_update_with_new_id(self, tmp_path):
        svc = _make_service(tmp_path)
        updated = svc.update_employee("100", id="999")
        assert updated.id == "999"
        assert svc.get_employee("999") is not None
        assert svc.get_employee("100") is None

    def test_update_with_conflicting_id_raises(self, tmp_path):
        svc = _make_service(tmp_path)
        with pytest.raises(ValueError, match="employee_exists"):
            svc.update_employee("100", id="200")


class TestEmployeeServiceArchive:
    def test_archive_inactive_employee(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.update_employee("100", status="inactive")
        archived = svc.archive_employee("100")
        assert archived is not None
        assert archived.archived is True
        assert archived.archived_at is not None

    def test_archive_active_raises(self, tmp_path):
        svc = _make_service(tmp_path)
        with pytest.raises(ValueError, match="employee_not_inactive"):
            svc.archive_employee("100")

    def test_archive_already_archived_is_noop(self, tmp_path):
        data = {"1": make_employee_dict("1", status="inactive", archived=True)}
        svc = _make_service(tmp_path, data)
        result = svc.archive_employee("1")
        assert result is not None
        assert result.archived is True

    def test_archive_nonexistent(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.archive_employee("999") is None


class TestEmployeeServiceRestore:
    def test_restore_archived(self, tmp_path):
        data = {"1": make_employee_dict("1", status="inactive", archived=True,
                                         archived_at=datetime.utcnow().isoformat())}
        svc = _make_service(tmp_path, data)
        restored = svc.restore_employee("1")
        assert restored is not None
        assert restored.archived is False
        assert restored.archived_at is None

    def test_restore_not_archived_is_noop(self, tmp_path):
        svc = _make_service(tmp_path)
        result = svc.restore_employee("100")
        assert result is not None
        assert result.archived is False

    def test_restore_nonexistent(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.restore_employee("999") is None


class TestEmployeeServiceRemove:
    def test_remove_employee(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.remove_employee("100")
        assert svc.get_employee("100") is None


class TestEmployeeServiceGet:
    def test_get_existing(self, tmp_path):
        svc = _make_service(tmp_path)
        emp = svc.get_employee("100")
        assert emp is not None

    def test_get_nonexistent(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.get_employee("999") is None


# ---------------------------------------------------------------------------
# EmployeeAPIService
# ---------------------------------------------------------------------------

class TestEmployeeAPIServiceList:
    def test_list_returns_employee_out(self, tmp_path):
        svc = _make_service(tmp_path)
        api = EmployeeAPIService(svc)

        async def _run():
            result = await api.list_employees()
            assert len(result) > 0
            assert hasattr(result[0], "id")
        run_async(_run())


class TestEmployeeAPIServiceCreate:
    def test_create_employee(self, tmp_path):
        svc = _make_service(tmp_path, data={})
        api = EmployeeAPIService(svc)

        async def _run():
            data = EmployeeCreate(name="Новый", full_name="Новый Сотрудник")
            result = await api.create_employee(data)
            assert result.name == "Новый"
        run_async(_run())

    def test_create_duplicate_raises_http_400(self, tmp_path):
        from fastapi import HTTPException
        svc = _make_service(tmp_path)
        api = EmployeeAPIService(svc)

        async def _run():
            data = EmployeeCreate(name="Дубль", id="100")
            with pytest.raises(HTTPException) as exc_info:
                await api.create_employee(data)
            assert exc_info.value.status_code == 400
        run_async(_run())


class TestEmployeeAPIServiceUpdate:
    def test_update_employee(self, tmp_path):
        svc = _make_service(tmp_path)
        api = EmployeeAPIService(svc)

        async def _run():
            data = EmployeeUpdate(name="Обновлён")
            result = await api.update_employee("100", data)
            assert result.name == "Обновлён"
        run_async(_run())

    def test_update_nonexistent_raises_404(self, tmp_path):
        from fastapi import HTTPException
        svc = _make_service(tmp_path)
        api = EmployeeAPIService(svc)

        async def _run():
            data = EmployeeUpdate(name="X")
            with pytest.raises(HTTPException) as exc_info:
                await api.update_employee("999", data)
            assert exc_info.value.status_code == 404
        run_async(_run())


class TestEmployeeAPIServiceArchiveRestore:
    def test_archive_via_api(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.update_employee("100", status="inactive")
        api = EmployeeAPIService(svc)

        async def _run():
            result = await api.archive_employee("100")
            assert result.archived is True
        run_async(_run())

    def test_archive_active_raises_400(self, tmp_path):
        from fastapi import HTTPException
        svc = _make_service(tmp_path)
        api = EmployeeAPIService(svc)

        async def _run():
            with pytest.raises(HTTPException) as exc_info:
                await api.archive_employee("100")
            assert exc_info.value.status_code == 400
        run_async(_run())

    def test_restore_via_api(self, tmp_path):
        data = {"1": make_employee_dict("1", status="inactive", archived=True,
                                         archived_at=datetime.utcnow().isoformat())}
        svc = _make_service(tmp_path, data)
        api = EmployeeAPIService(svc)

        async def _run():
            result = await api.restore_employee("1")
            assert result.archived is False
        run_async(_run())


class TestEmployeeAPIServiceDelete:
    def test_delete_employee(self, tmp_path):
        svc = _make_service(tmp_path)
        api = EmployeeAPIService(svc)

        async def _run():
            result = await api.delete_employee("100")
            assert result["status"] == "deleted"
        run_async(_run())

    def test_delete_nonexistent_raises_404(self, tmp_path):
        from fastapi import HTTPException
        svc = _make_service(tmp_path)
        api = EmployeeAPIService(svc)

        async def _run():
            with pytest.raises(HTTPException) as exc_info:
                await api.delete_employee("999")
            assert exc_info.value.status_code == 404
        run_async(_run())


class TestNormalizeStatus:
    def test_from_enum(self):
        assert EmployeeService._normalize_status(EmployeeStatus.ACTIVE) == EmployeeStatus.ACTIVE

    def test_from_string(self):
        assert EmployeeService._normalize_status("inactive") == EmployeeStatus.INACTIVE

    def test_from_none(self):
        assert EmployeeService._normalize_status(None) == EmployeeStatus.ACTIVE
