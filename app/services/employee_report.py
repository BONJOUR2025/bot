from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import List

from fastapi import HTTPException
from dateutil.relativedelta import relativedelta
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for type hints only
    from app.data.employee_repository import EmployeeRepository
    from app.data.payout_repository import PayoutRepository
    from app.data.vacation_repository import VacationRepository


class EmployeeReportService:
    def __init__(
        self,
        employee_repo: EmployeeRepository,
        payout_repo: PayoutRepository,
        vacation_repo: VacationRepository,
    ) -> None:
        self.employee_repo = employee_repo
        self.payout_repo = payout_repo
        self.vacation_repo = vacation_repo

    def _parse_ts(self, ts: str) -> datetime | None:
        try:
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

    def generate_profile_pdf(self, employee_id: str) -> bytes:
        employees = self.employee_repo.list_employees()
        employee = next((e for e in employees if str(e.id) == str(employee_id)), None)
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        cutoff = datetime.now() - relativedelta(months=3)
        payouts = [
            p
            for p in self.payout_repo.list(employee_id=str(employee_id))
            if (self._parse_ts(p.get("timestamp")) or datetime.min) >= cutoff
        ]
        vacations = [
            v
            for v in self.vacation_repo.list()
            if str(v.get("employee_id")) == str(employee_id)
        ]

        status_counts: dict[str, int] = {}
        for p in payouts:
            status = p.get("status", "")
            status_counts[status] = status_counts.get(status, 0) + 1

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)

        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        bold_font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        pdfmetrics.registerFont(TTFont("DejaVu", font))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", bold_font))

        y = 800
        pdf.setFont("DejaVu-Bold", 16)
        pdf.drawString(40, y, "👤 PERSONAL DETAILS")
        y -= 24
        pdf.setFont("DejaVu", 12)
        pdf.drawString(50, y, f"Full name: {employee.full_name}")
        y -= 15
        pdf.drawString(50, y, f"Telegram ID: {employee.id}")
        y -= 15
        if employee.birthdate:
            pdf.drawString(50, y, f"Birthday: {employee.birthdate}")
            y -= 15
        pdf.drawString(50, y, f"Code: {employee.name}")
        y -= 30

        pdf.setFont("DejaVu-Bold", 14)
        pdf.drawString(40, y, "💸 PAYOUT HISTORY")
        y -= 20
        pdf.setFont("DejaVu", 12)
        for p in payouts:
            line = (
                f"{p.get('timestamp','')} | {p.get('amount')} ₽ | "
                f"{p.get('payout_type','')} | {p.get('method','')} | {p.get('status','')}"
            )
            pdf.drawString(50, y, line)
            y -= 15
            if y < 60:
                pdf.showPage()
                y = 800
                pdf.setFont("DejaVu", 12)

        pdf.setFont("DejaVu-Bold", 14)
        pdf.drawString(40, y, "📅 VACATION")
        y -= 20
        pdf.setFont("DejaVu", 12)
        for v in vacations:
            line = f"{v.get('start_date')} → {v.get('end_date')}"
            pdf.drawString(50, y, line)
            y -= 15
            if y < 60:
                pdf.showPage()
                y = 800
                pdf.setFont("DejaVu", 12)

        pdf.setFont("DejaVu-Bold", 14)
        pdf.drawString(40, y, "📊 STATS")
        y -= 20
        pdf.setFont("DejaVu", 12)
        for status, count in status_counts.items():
            pdf.drawString(50, y, f"{status}: {count}")
            y -= 15
            if y < 60:
                pdf.showPage()
                y = 800
                pdf.setFont("DejaVu", 12)
        pdf.drawString(50, y - 10, f"📆 Generated: {datetime.now().strftime('%Y-%m-%d')}")
        pdf.showPage()
        pdf.save()
        buffer.seek(0)
        return buffer.getvalue()
