"""Employee helper functions using the local repository."""

from datetime import datetime
from typing import Any, Dict, List

from app.core.types import Employee, EmployeeStatus
from app.data.employee_repository import EmployeeRepository
from ..utils.logger import log

_repo = EmployeeRepository()


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def load_users(archived: bool | None = False) -> List[Dict[str, Any]]:
    """Return users as a list of objects suitable for frontend.

    Args:
        archived: Archive filter passed to the repository. ``False`` returns only
            active employees, ``True`` returns only archived ones and ``None``
            returns everyone.
    """
    path = getattr(_repo, "_storage").path
    log(f"📂 Загрузка сотрудников из: {path}")
    result: List[Dict[str, Any]] = []
    for emp in _repo.list_employees(archived=archived):
        result.append(
            {
                "id": int(emp.id) if str(emp.id).isdigit() else emp.id,
                "name": emp.name,
                "full_name": emp.full_name,
                "phone": emp.phone,
                "position": emp.position,
                "is_admin": emp.is_admin,
                "card_number": emp.card_number,
                "bank": emp.bank,
                "birthdate": emp.birthdate.isoformat() if emp.birthdate else None,
                "note": emp.note,
                "photo_url": emp.photo_url,
                "status": emp.status.value,
                "payout_chat_key": getattr(emp, "payout_chat_key", None),
                "archived": getattr(emp, "archived", False),
                "archived_at": emp.archived_at.isoformat() if emp.archived_at else None,
            }
        )
    log(f"✅ Загружено сотрудников: {len(result)}")
    return result


def load_users_map(archived: bool | None = False) -> Dict[str, Any]:
    """Return users keyed by id for legacy handlers."""

    return {
        str(u["id"]): {k: v for k, v in u.items() if k != "id"}
        for u in load_users(archived=archived)
    }


def save_users(users: Dict[str, Any]) -> None:
    """Persist provided user dict via the repository."""
    employees = []
    for uid, data in users.items():
        employees.append(
            Employee(
                id=str(uid),
                name=data.get("name", ""),
                full_name=data.get("full_name", ""),
                phone=data.get("phone", ""),
                position=data.get("position", ""),
                is_admin=data.get("is_admin", False),
                card_number=data.get("card_number", ""),
                bank=data.get("bank", ""),
                birthdate=data.get("birthdate"),
                note=data.get("note", ""),
                photo_url=data.get("photo_url", ""),
                status=EmployeeStatus(data.get("status", "active")),
                payout_chat_key=data.get("payout_chat_key"),
                archived=data.get("archived", False),
                archived_at=_parse_datetime(data.get("archived_at")),
            )
        )
    _repo.save_employees(employees)

def add_user(user_id: str, user_data: Dict[str, Any]) -> None:
    employee = Employee(
        id=str(user_id),
        name=user_data.get("name", ""),
        full_name=user_data.get("full_name", ""),
        phone=user_data.get("phone", ""),
        position=user_data.get("position", ""),
        is_admin=user_data.get("is_admin", False),
        card_number=user_data.get("card_number", ""),
        bank=user_data.get("bank", ""),
        birthdate=user_data.get("birthdate"),
        note=user_data.get("note", ""),
        photo_url=user_data.get("photo_url", ""),
        status=EmployeeStatus(user_data.get("status", "active")),
        payout_chat_key=user_data.get("payout_chat_key"),
        archived=user_data.get("archived", False),
        archived_at=_parse_datetime(user_data.get("archived_at")),
    )
    _repo.add_employee(employee)


def update_user(user_id: str, fields: Dict[str, Any]) -> None:
    emp_dict = load_users_map(archived=None).get(str(user_id))
    if not emp_dict:
        log(f"⚠️ update_user: user {user_id} not found")
        return
    normalized_fields = dict(fields)
    if "archived_at" in normalized_fields:
        value = normalized_fields["archived_at"]
        if isinstance(value, datetime):
            normalized_fields["archived_at"] = value.isoformat()
        elif value is not None:
            normalized_fields["archived_at"] = str(value)
    emp_dict.update(normalized_fields)
    if "archived" in normalized_fields:
        if emp_dict.get("archived"):
            if not emp_dict.get("archived_at"):
                emp_dict["archived_at"] = datetime.utcnow().isoformat()
        else:
            emp_dict["archived_at"] = None
    employee = Employee(
        id=str(user_id),
        name=emp_dict.get("name", ""),
        full_name=emp_dict.get("full_name", ""),
        phone=emp_dict.get("phone", ""),
        position=emp_dict.get("position", ""),
        is_admin=emp_dict.get("is_admin", False),
        card_number=emp_dict.get("card_number", ""),
        bank=emp_dict.get("bank", ""),
        birthdate=emp_dict.get("birthdate"),
        note=emp_dict.get("note", ""),
        photo_url=emp_dict.get("photo_url", ""),
        status=EmployeeStatus(emp_dict.get("status", "active")),
        payout_chat_key=emp_dict.get("payout_chat_key"),
        archived=emp_dict.get("archived", False),
        archived_at=_parse_datetime(emp_dict.get("archived_at")),
    )
    _repo.update_employee(employee)


def delete_user(user_id: str) -> None:
    _repo.delete_employee_by_id(str(user_id))
