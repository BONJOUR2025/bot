"""PDF profile generation service."""

from typing import TYPE_CHECKING

from .employee_report import EmployeeReportService

if TYPE_CHECKING:  # pragma: no cover - for type hints only
    from app.data.employee_repository import EmployeeRepository
    from app.data.payout_repository import PayoutRepository
    from app.data.vacation_repository import VacationRepository


def generate_employee_pdf(
    user_id: int,
    employee_repo: "EmployeeRepository",
    payout_repo: "PayoutRepository",
    vacation_repo: "VacationRepository",
) -> bytes:
    """Return PDF profile for the given employee ID."""
    service = EmployeeReportService(employee_repo, payout_repo, vacation_repo)
    return service.generate_profile_pdf(str(user_id))

