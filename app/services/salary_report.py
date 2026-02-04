from __future__ import annotations

import os
from io import BytesIO
from typing import Iterable

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.schemas.salary import SalaryRow
from app.config import FONT_PATH


def generate_salary_pdf(rows: Iterable[SalaryRow], month: str) -> bytes:
    """Generate a simple salary PDF report."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)

    font = FONT_PATH
    bold_font = font.replace(".ttf", "-Bold.ttf")
    if os.path.exists(font):
        pdfmetrics.registerFont(TTFont("Arial", font))
        if os.path.exists(bold_font):
            pdfmetrics.registerFont(TTFont("Arial-Bold", bold_font))
        font_name = "Arial"
        bold_name = "Arial-Bold" if os.path.exists(bold_font) else "Arial"
    else:
        font_name = "Helvetica"
        bold_name = "Helvetica-Bold"

    y = 800
    pdf.setFont(bold_name, 16)
    pdf.drawString(40, y, f"\uD83D\uDCB0 SALARY REPORT - {month}")
    y -= 24

    pdf.setFont(bold_name, 12)
    pdf.drawString(50, y, "Name | Shifts | Total ₽ | Final ₽")
    y -= 18
    pdf.setFont(font_name, 12)

    for r in rows:
        line = f"{r.name} | {r.shifts_total} | {r.salary_total:.2f} | {r.final_amount:.2f}"
        pdf.drawString(50, y, line)
        y -= 15
        if y < 60:
            pdf.showPage()
            y = 800
            pdf.setFont(font_name, 12)

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()
