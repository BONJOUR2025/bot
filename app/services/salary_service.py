from __future__ import annotations

from typing import List, Optional

import pandas as pd

from .excel import load_data
from ..data.employee_repository import EmployeeRepository
from ..schemas.salary import SalaryRow


class SalaryService:
    """Service to load salary data from Excel."""

    def __init__(self, repo: EmployeeRepository | None = None) -> None:
        self._repo = repo or EmployeeRepository()
        self._cache: dict[str, pd.DataFrame] = {}

    def _load_month(self, month: str) -> pd.DataFrame | None:
        month = month.upper()
        if month in self._cache:
            return self._cache[month]
        df = load_data(sheet_name=month)
        if df is not None:
            df.columns = [str(c).strip() for c in df.columns]
            self._cache[month] = df
        return df

    async def list_months(self) -> List[str]:
        months = load_data(None)
        return months or []

    async def get_salary(
        self, month: Optional[str] = None, employee_id: Optional[str] = None
    ) -> List[SalaryRow]:
        if not month:
            return []
        df = self._load_month(month)
        if df is None or "ИМЯ" not in df.columns:
            return []
        name_map = {e.name: e.id for e in self._repo.list_employees()}
        result: List[SalaryRow] = []
        cols = {str(c).strip().lower(): c for c in df.columns}

        def pick(*names: str) -> Optional[str]:
            for n in names:
                key = str(n).strip().lower()
                if key in cols:
                    return cols[key]
            return None

        colmap = {
            "shifts_main": pick("осн.", "основные", "shifts_main"),
            "shifts_extra": pick("доп.", "дополнительные", "shifts_extra"),
            "shifts_total": pick("общ", "итого смен", "shifts_total"),
            "salary_fixed": pick("оклад", "salary_fixed"),
            "salary_repair": pick("ремонт", "salary_repair"),
            "salary_cosmetics": pick("косметика", "salary_cosmetics"),
            "salary_shoes": pick("обувь", "salary_shoes"),
            "salary_accessories": pick("аксессуары", "salary_accessories"),
            "salary_keys": pick("ключи", "salary_keys"),
            "salary_slippers": pick("тапки", "salary_slippers"),
            "salary_workshop": pick("цех", "workshop", "salary_workshop"),
            "salary_bonus": pick("бонус", "salary_bonus"),
            "salary_total": pick("итого", "salary_total"),
            "deduction": pick("удержание", "deduction"),
            "advance": pick("аванс", "advance"),
            "final_amount": pick("к выплате", "final_amount"),
            "comment": pick("комментарий", "comment"),
        }
        for _, row in df.iterrows():
            name = str(row.get("ИМЯ", "")).strip()
            if not name:
                continue
            emp_id = name_map.get(name, "")
            if employee_id and emp_id != employee_id:
                continue

            def to_float(val: object) -> float:
                try:
                    if pd.isna(val):
                        return 0.0
                    return float(val)
                except Exception:
                    return 0.0

            def to_int(val: object) -> int:
                try:
                    if pd.isna(val):
                        return 0
                    return int(float(val))
                except Exception:
                    return 0

            values = {}
            for field, col in colmap.items():
                if col is None:
                    if field == "comment":
                        values[field] = ""
                    else:
                        values[field] = 0
                    continue
                if field.startswith("shifts_"):
                    values[field] = to_int(row.get(col))
                elif field in {"comment"}:
                    values[field] = str(row.get(col, "")).strip()
                else:
                    values[field] = to_float(row.get(col))

            if values.get("shifts_total") == 0:
                values["shifts_total"] = values.get(
                    "shifts_main", 0) + values.get("shifts_extra", 0)

            comment_raw = values.pop("comment", "")
            comment = str(comment_raw).strip() or None
            result.append(
                SalaryRow(
                    employee_id=emp_id,
                    name=name,
                    month=month,
                    comment=comment,
                    **values,
                )
            )
        return result
