from datetime import datetime

import pytest

from app.core.enums import EmployeeStatus
from app.core.types import Employee
from app.services.employee_service import EmployeeService


class InMemoryEmployeeRepo:
    def __init__(self, employees: list[Employee]) -> None:
        self._employees = {emp.id: emp for emp in employees}

    def list_employees(self, archived=None):
        employees = list(self._employees.values())
        if archived is None:
            return employees
        return [emp for emp in employees if emp.archived == archived]

    def add_employee(self, employee: Employee) -> None:
        self._employees[employee.id] = employee

    def update_employee(self, employee: Employee) -> None:
        self._employees[employee.id] = employee

    def delete_employee_by_id(self, employee_id: str) -> None:
        self._employees.pop(employee_id, None)


def make_employee(emp_id: str, status: EmployeeStatus) -> Employee:
    return Employee(
        id=emp_id,
        name=f"Emp {emp_id}",
        full_name=f"Employee {emp_id}",
        phone="70000000000",
        status=status,
    )


def test_archive_and_restore_employee_updates_flags_and_filters():
    inactive = make_employee("1", EmployeeStatus.INACTIVE)
    active = make_employee("2", EmployeeStatus.ACTIVE)
    repo = InMemoryEmployeeRepo([inactive, active])
    service = EmployeeService(repo)

    archived = service.archive_employee("1")

    assert archived is not None
    assert archived.archived is True
    assert isinstance(archived.archived_at, datetime)
    assert [emp.id for emp in service.list_employees()] == ["2"]
    assert [emp.id for emp in service.list_employees(archived=True)] == ["1"]

    restored = service.restore_employee("1")

    assert restored is not None
    assert restored.archived is False
    assert restored.archived_at is None
    assert sorted(emp.id for emp in service.list_employees()) == ["1", "2"]


def test_archive_employee_requires_inactive_status():
    repo = InMemoryEmployeeRepo([make_employee("42", EmployeeStatus.ACTIVE)])
    service = EmployeeService(repo)

    with pytest.raises(ValueError):
        service.archive_employee("42")


def test_archive_employee_with_string_status_after_update():
    repo = InMemoryEmployeeRepo([make_employee("5", EmployeeStatus.INACTIVE)])
    service = EmployeeService(repo)

    # emulate API update that passes status as a raw string
    updated = service.update_employee("5", status="inactive")

    assert updated is not None
    assert isinstance(updated.status, EmployeeStatus)

    archived = service.archive_employee("5")

    assert archived is not None
    assert archived.archived is True
