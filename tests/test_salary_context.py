"""Tests for app.services.salary_context.get_salary_context -- the payout
form's "position -> whichever system computes this person's pay" router.

Each branch is exercised in isolation by monkeypatching exactly the call
salary_context makes into that system, not by re-testing those systems
themselves (masters_service/payroll_service/manager_salary_repository/
courier_salary_repository already have their own test suites).
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.services import salary_context


class _FakeEmployeeRepo:
    def __init__(self, employees):
        self._employees = employees

    def get_employee(self, employee_id):
        return self._employees.get(str(employee_id))


def _employee(position="", name="Иван 1001", full_name="Иванов Иван Иванович"):
    return SimpleNamespace(position=position, name=name, full_name=full_name)


class _FakePayoutRepo:
    def advances_since_last_salary(self, employee_id):
        return {"total": 100.0, "count": 1, "since": "2026-07-01 00:00:00"}


@pytest.fixture(autouse=True)
def _no_advances(monkeypatch):
    """Advances are computed via PayoutRepository.advances_since_last_salary
    (already tested in test_advances_since_last_salary.py) -- stub it to a
    fixed value so every branch's total_salary/to_pay math is checked
    against a known deduction."""
    monkeypatch.setattr(salary_context, "PayoutRepository", lambda: _FakePayoutRepo())


class TestNotFound:
    def test_unknown_employee_returns_not_found(self, monkeypatch):
        monkeypatch.setattr(salary_context, "EmployeeRepository", lambda: _FakeEmployeeRepo({}))
        result = asyncio.run(salary_context.get_salary_context("999"))
        assert result == {"found": False}


class TestMonthEnd:
    def test_current_month_ends_today_not_the_calendar_end(self):
        from datetime import date
        today = date.today()
        assert salary_context._month_end(today.year, today.month) == today

    def test_past_month_ends_on_its_calendar_last_day(self):
        from datetime import date
        assert salary_context._month_end(2026, 7) == date(2026, 7, 31)
        assert salary_context._month_end(2024, 2) == date(2024, 2, 29)  # leap year


class TestPositionRole:
    @pytest.mark.parametrize("position,expected", [
        ("Мастер маникюра", "master"),
        ("Курьер", "courier"),
        ("Менеджер по продажам", "manager"),
        ("Администратор", "staff"),
        ("", "staff"),
    ])
    def test_role_from_position(self, position, expected):
        assert salary_context._position_role(position) == expected


class TestMasterBranch:
    def test_master_gross_and_to_pay(self, monkeypatch):
        employee = _employee(position="Мастер маникюра")
        monkeypatch.setattr(salary_context, "EmployeeRepository",
                             lambda: _FakeEmployeeRepo({"7": employee}))

        from app.services import masters_service
        monkeypatch.setattr(masters_service, "FIREBIRD_AVAILABLE", True)

        async def fake_run_with_timeout(fn, *, date_from, date_to, timeout):
            return {"salary_summary": [{"master": "Х", "total_salary": 50000.0}]}

        monkeypatch.setattr(
            "app.services.firebird_service.run_with_timeout", fake_run_with_timeout
        )
        monkeypatch.setattr(
            masters_service, "find_master_salary_row",
            lambda employee_id, summary: summary[0],
        )

        result = asyncio.run(salary_context.get_salary_context("7"))
        assert result["found"] is True
        assert result["role"] == "master"
        assert result["total_salary"] == 50000.0
        assert result["advances_since_last_salary"] == 100.0
        assert result["to_pay"] == 49900.0
        assert result["note"] is None

    def test_master_not_found_in_report_gives_note_not_zero(self, monkeypatch):
        employee = _employee(position="Мастер маникюра")
        monkeypatch.setattr(salary_context, "EmployeeRepository",
                             lambda: _FakeEmployeeRepo({"7": employee}))

        from app.services import masters_service
        monkeypatch.setattr(masters_service, "FIREBIRD_AVAILABLE", True)

        async def fake_run_with_timeout(fn, *, date_from, date_to, timeout):
            return {"salary_summary": []}

        monkeypatch.setattr(
            "app.services.firebird_service.run_with_timeout", fake_run_with_timeout
        )
        monkeypatch.setattr(masters_service, "find_master_salary_row", lambda *a: None)

        result = asyncio.run(salary_context.get_salary_context("7"))
        assert result["total_salary"] is None
        assert result["to_pay"] is None
        assert result["note"]

    def test_firebird_unavailable_gives_note(self, monkeypatch):
        employee = _employee(position="Мастер маникюра")
        monkeypatch.setattr(salary_context, "EmployeeRepository",
                             lambda: _FakeEmployeeRepo({"7": employee}))
        from app.services import masters_service
        monkeypatch.setattr(masters_service, "FIREBIRD_AVAILABLE", False)

        result = asyncio.run(salary_context.get_salary_context("7"))
        assert result["total_salary"] is None
        assert "Firebird" in result["note"]


class TestAccrualBranches:
    def test_courier_reads_current_period_accrual(self, monkeypatch):
        employee = _employee(position="Курьер")
        monkeypatch.setattr(salary_context, "EmployeeRepository",
                             lambda: _FakeEmployeeRepo({"3": employee}))

        class FakeRepo:
            def list(self, *, employee_code, period, limit):
                assert employee_code == "3"
                assert limit == 1
                return [{"result": {"gross": 20000.0}}]

        monkeypatch.setattr(
            "app.data.courier_salary_repository.get_courier_salary_repository",
            lambda: FakeRepo(),
        )

        result = asyncio.run(salary_context.get_salary_context("3"))
        assert result["role"] == "courier"
        assert result["total_salary"] == 20000.0
        assert result["to_pay"] == 19900.0

    def test_explicit_year_month_overrides_the_current_period(self, monkeypatch):
        """A payout created early in a new month is usually for the previous
        one's accrual -- the caller must be able to ask for a period other
        than "right now"."""
        employee = _employee(position="Курьер")
        monkeypatch.setattr(salary_context, "EmployeeRepository",
                             lambda: _FakeEmployeeRepo({"3": employee}))

        seen_periods = []

        class FakeRepo:
            def list(self, *, employee_code, period, limit):
                seen_periods.append(period)
                return [{"result": {"gross": 20000.0}}]

        monkeypatch.setattr(
            "app.data.courier_salary_repository.get_courier_salary_repository",
            lambda: FakeRepo(),
        )

        asyncio.run(salary_context.get_salary_context("3", year=2026, month=7))
        assert seen_periods == ["2026-07"]

    def test_manager_with_no_accrual_yet_gives_note_not_zero(self, monkeypatch):
        employee = _employee(position="Менеджер по продажам")
        monkeypatch.setattr(salary_context, "EmployeeRepository",
                             lambda: _FakeEmployeeRepo({"4": employee}))

        class FakeRepo:
            def list(self, *, employee_code, period, limit):
                return []

        monkeypatch.setattr(
            "app.data.manager_salary_repository.get_manager_salary_repository",
            lambda: FakeRepo(),
        )

        result = asyncio.run(salary_context.get_salary_context("4"))
        assert result["role"] == "manager"
        assert result["total_salary"] is None
        assert result["to_pay"] is None
        assert result["note"]


class TestStaffBranch:
    def test_staff_uses_payroll_service_by_extracted_code(self, monkeypatch):
        employee = _employee(position="Администратор", name="Мария 2044")
        monkeypatch.setattr(salary_context, "EmployeeRepository",
                             lambda: _FakeEmployeeRepo({"9": employee}))

        class FakePayrollService:
            async def get_employee_details(self, code, month, year):
                assert code == "2044"
                return SimpleNamespace(total_gross=35000.0)

        monkeypatch.setattr(
            "app.services.payroll_service.PayrollService", FakePayrollService
        )

        result = asyncio.run(salary_context.get_salary_context("9"))
        assert result["role"] == "staff"
        assert result["total_salary"] == 35000.0
        assert result["to_pay"] == 34900.0

    def test_staff_without_extractable_code_gives_note(self, monkeypatch):
        employee = _employee(position="Администратор", name="Без кода")
        monkeypatch.setattr(salary_context, "EmployeeRepository",
                             lambda: _FakeEmployeeRepo({"9": employee}))

        result = asyncio.run(salary_context.get_salary_context("9"))
        assert result["total_salary"] is None
        assert result["note"]
