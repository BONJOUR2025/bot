from __future__ import annotations

from datetime import date, timedelta
from typing import List, Dict

from app.data.employee_repository import EmployeeRepository
from app.core.enums import EmployeeStatus

_repo = EmployeeRepository()


def get_upcoming_birthdays(days_ahead: int = 1) -> List[Dict[str, str]]:
    """Return active employees with birthdays in the next ``days_ahead`` days."""
    if days_ahead < 0:
        days_ahead = 0
    today = date.today()
    employees = _repo.list_employees(archived=False)
    result: List[Dict[str, str]] = []
    for emp in employees:
        if emp.status != EmployeeStatus.ACTIVE:
            continue
        bday = emp.birthdate
        if not isinstance(bday, date):
            continue
        if bday.year < 1900:
            continue
        for offset in range(days_ahead + 1):
            target = today + timedelta(days=offset)
            if bday.month == target.month and bday.day == target.day:
                result.append(
                    {
                        "user_id": emp.id,
                        "full_name": emp.full_name or emp.name,
                        "birthdate": bday.isoformat(),
                        "phone": emp.phone,
                    }
                )
                break

    def sort_key(item: Dict[str, str]) -> date:
        b = date.fromisoformat(item["birthdate"])
        d = date(today.year, b.month, b.day)
        if d < today:
            d = d.replace(year=today.year + 1)
        return d

    result.sort(key=sort_key)
    return result
