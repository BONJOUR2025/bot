from enum import Enum


class EmployeeStatus(Enum):
    """Employee active/inactive status."""

    ACTIVE = "active"
    INACTIVE = "inactive"


# Unified payout status list used across backend and frontend
PAYOUT_STATUSES = ["Ожидает", "Одобрено", "Отклонено", "Выплачено"]

# Unified leave request status list used across backend and frontend
LEAVE_REQUEST_STATUSES = ["Ожидает", "Одобрено", "Отклонено"]
