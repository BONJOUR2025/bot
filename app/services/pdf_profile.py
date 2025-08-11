"""PDF profile generation service using ``fpdf``."""
from typing import TYPE_CHECKING
from fpdf import FPDF
import os

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
    """Generate a small PDF file with basic employee information."""
    employees = employee_repo.list_employees()
    employee = next((e for e in employees if str(e.id) == str(user_id)), None)
    if not employee:
        raise ValueError("Employee not found")

    payouts = payout_repo.list(employee_id=str(user_id))
    vacations = [v for v in vacation_repo.list() if str(v.get("employee_id")) == str(user_id)]

    pdf = FPDF()
    pdf.add_page()

    font_path = "fonts/DejaVuSans.ttf"

    def safe(text: str) -> str:
        if os.path.exists(font_path):
            return str(text)
        return str(text).encode("ascii", "ignore").decode("ascii")

    if os.path.exists(font_path):
        pdf.add_font("DejaVu", style="", fname=font_path, uni=True)
        pdf.set_font("DejaVu", size=12)
    else:
        pdf.set_font("Helvetica", size=12)

    pdf.cell(0, 10, safe("PERSONAL DETAILS"), ln=True)
    pdf.cell(0, 10, safe(f"Full name: {getattr(employee, 'full_name', '')}"), ln=True)
    pdf.cell(0, 10, safe(f"Telegram ID: {employee.id}"), ln=True)
    pdf.cell(0, 10, safe(f"Code: {getattr(employee, 'name', '')}"), ln=True)
    pdf.ln(5)
    pdf.cell(0, 10, safe("PAYOUT HISTORY"), ln=True)
    for p in payouts:
        line = safe(f"{p.get('timestamp', '')} | {p.get('amount')} RUB | {p.get('status', '')}")
        pdf.cell(0, 10, line, ln=True)
    pdf.ln(5)
    pdf.cell(0, 10, safe("VACATION"), ln=True)
    for v in vacations:
        pdf.cell(0, 10, safe(f"{v.get('start_date')} -> {v.get('end_date')}"), ln=True)
    pdf.ln(5)
    pdf.cell(0, 10, safe("STATS"), ln=True)
    status_counts = {}
    for p in payouts:
        status = p.get("status", "")
        status_counts[status] = status_counts.get(status, 0) + 1
    for status, count in status_counts.items():
        pdf.cell(0, 10, safe(f"{status}: {count}"), ln=True)

    return pdf.output(dest="S").encode("latin-1")


def generate_employees_list_pdf(employees) -> bytes:
    """Generate a PDF listing all employees."""

    pdf = FPDF()
    pdf.add_page()

    font_path = "fonts/DejaVuSans.ttf"

    def safe(text: str) -> str:
        if os.path.exists(font_path):
            return str(text)
        return str(text).encode("ascii", "ignore").decode("ascii")

    if os.path.exists(font_path):
        pdf.add_font("DejaVu", style="", fname=font_path, uni=True)
        pdf.set_font("DejaVu", size=12)
    else:
        pdf.set_font("Helvetica", size=12)

    pdf.cell(0, 10, safe("EMPLOYEE LIST"), ln=True)

    for emp in employees:
        line = safe(
            f"{getattr(emp, 'full_name', '')} | {emp.position} | {emp.phone}"
        )
        pdf.cell(0, 10, line, ln=True)

    return pdf.output(dest="S").encode("latin-1")
