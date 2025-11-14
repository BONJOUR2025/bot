from datetime import datetime

from app.core.types import Employee, EmployeeStatus
from app.data.employee_repository import EmployeeRepository
from app.data.json_storage import JsonStorage
from app.services import users as users_service


def _setup_repo(tmp_path, monkeypatch) -> EmployeeRepository:
    storage = JsonStorage(tmp_path / "users.json")
    repo = EmployeeRepository(storage=storage)
    repo.save_employees([])
    monkeypatch.setattr(users_service, "_repo", repo)
    return repo


def _make_employee(emp_id: str, archived: bool = False, archived_at: datetime | None = None) -> Employee:
    return Employee(
        id=emp_id,
        name=f"Emp {emp_id}",
        full_name=f"Employee {emp_id}",
        phone="70000000000",
        status=EmployeeStatus.INACTIVE,
        archived=archived,
        archived_at=archived_at,
    )


def test_update_user_sets_archive_flag_and_timestamp(monkeypatch, tmp_path):
    repo = _setup_repo(tmp_path, monkeypatch)
    repo.add_employee(_make_employee("1"))

    users_service.update_user("1", {"archived": True})

    updated = repo.get_employee("1")
    assert updated is not None
    assert updated.archived is True
    assert isinstance(updated.archived_at, datetime)


def test_update_user_clears_timestamp_when_restoring(monkeypatch, tmp_path):
    repo = _setup_repo(tmp_path, monkeypatch)
    archived_at = datetime.utcnow()
    repo.add_employee(_make_employee("2", archived=True, archived_at=archived_at))

    users_service.update_user("2", {"archived": False})

    updated = repo.get_employee("2")
    assert updated is not None
    assert updated.archived is False
    assert updated.archived_at is None
