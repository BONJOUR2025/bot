from __future__ import annotations

from datetime import date
from typing import Dict, List

import os
from openpyxl import load_workbook

from ..config import EXCEL_FILE
from ..schemas.schedule import SchedulePointOut
from ..core.constants import MONTHS_RU

POINTS = {
    "Ц": "Цех",
    "Ох": "Охта",
    "М": "Меркурий",
    "А": "Академка",
    "Оз": "Озерки",
    "П": "Пассаж",
    "Р": "Рио",
}


class ScheduleService:
    """Load schedule from Excel by day."""

    def __init__(self) -> None:
        pass

    async def get_schedule_by_day(
            self, date_str: str) -> List[SchedulePointOut]:
        """Return list of points and assigned employees for given date."""

        try:
            day_date = date.fromisoformat(date_str)
        except Exception:
            return []

        month_name = MONTHS_RU[day_date.month - 1]

        if not os.path.exists(EXCEL_FILE):
            return [
                SchedulePointOut(point=name, short=code, employee="")
                for code, name in POINTS.items()
            ]

        try:
            wb = load_workbook(EXCEL_FILE, data_only=True)
        except Exception:
            return [
                SchedulePointOut(point=name, short=code, employee="")
                for code, name in POINTS.items()
            ]

        sheet = None
        if month_name in wb.sheetnames:
            sheet = wb[month_name]
        elif month_name.upper() in wb.sheetnames:
            sheet = wb[month_name.upper()]
        else:
            for title in wb.sheetnames:
                if title.startswith(month_name) or title.startswith(
                        month_name.upper()):
                    sheet = wb[title]
                    break

        if sheet is None:
            return [
                SchedulePointOut(point=name, short=code, employee="")
                for code, name in POINTS.items()
            ]

        day_col = None
        target = str(day_date.day)
        for col in range(1, sheet.max_column + 1):
            v1 = str(sheet.cell(row=1, column=col).value or "").strip()
            v2 = str(sheet.cell(row=2, column=col).value or "").strip()
            if v1 == target or v2 == target:
                day_col = col
                break

        if day_col is None:
            return [
                SchedulePointOut(point=name, short=code, employee="")
                for code, name in POINTS.items()
            ]

        assignments: Dict[str, str] = {}
        for row in range(3, sheet.max_row + 1):
            code = str(sheet.cell(row=row, column=day_col).value or "").strip()
            if code not in POINTS or code in assignments:
                continue
            employee_cell = sheet.cell(row=row, column=1).value
            employee_name = str(employee_cell).strip() if employee_cell else ""
            assignments[code] = employee_name
            if len(assignments) == len(POINTS):
                break

        return [
            SchedulePointOut(
                point=name,
                short=code,
                employee=assignments.get(code, ""),
            )
            for code, name in POINTS.items()
        ]
