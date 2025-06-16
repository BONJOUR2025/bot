from __future__ import annotations

from typing import List, Optional

import pandas as pd

from .excel import load_data
from ..data.repository import Repository
from ..schemas.salary import SalaryRow


class SalaryService:
    """Service to load salary data from Excel."""

    def __init__(self, repo: Repository | None = None) -> None:
        self._repo = repo or Repository()
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
        cols = {c.lower(): c for c in df.columns}
        def pick(*names: str) -> Optional[str]:
            for n in names:
                key = n.lower()
                if key in cols:
                    return cols[key]
            return None

        base_col = pick("ОКЛАД", "base_salary", "оклад")
        kpi_col = pick("KPI", "kpi_bonus", "Премия (KPI)")
        bonus_col = pick("Бонусы", "attendance_bonus", "Бонус", "Бонус за посещаемость")
        deduct_col = pick("Удержание", "Удержания", "deductions")
        final_col = pick("К выплате", "final_amount")
        comment_col = pick("Комментарий", "comment")
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

            base = to_float(row.get(base_col))
            kpi = to_float(row.get(kpi_col))
            bonus = to_float(row.get(bonus_col))
            deduct = to_float(row.get(deduct_col))
            final_amt = to_float(row.get(final_col))
            comment = str(row.get(comment_col, "")).strip() if comment_col else ""
            result.append(
                SalaryRow(
                    employee_id=emp_id,
                    name=name,
                    month=month,
                    base_salary=base,
                    kpi_bonus=kpi,
                    attendance_bonus=bonus,
                    deductions=deduct,
                    final_amount=final_amt,
                    comment=comment or None,
                )
            )
        return result
