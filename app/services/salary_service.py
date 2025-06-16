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
        amount_col = "К выплате" if "К выплате" in df.columns else None
        comment_col = "Комментарий" if "Комментарий" in df.columns else None
        for _, row in df.iterrows():
            name = str(row.get("ИМЯ", "")).strip()
            if not name:
                continue
            emp_id = name_map.get(name, "")
            if employee_id and emp_id != employee_id:
                continue
            amount_val = row.get(amount_col, 0) if amount_col else 0
            try:
                amount = float(amount_val)
            except Exception:
                amount = 0.0
            comment = str(row.get(comment_col, "")).strip() if comment_col else ""
            result.append(
                SalaryRow(
                    employee_id=emp_id,
                    name=name,
                    month=month,
                    amount=amount,
                    comment=comment or None,
                )
            )
        return result
