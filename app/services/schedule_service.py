from __future__ import annotations

from datetime import date
from typing import List, Optional, Dict

import pandas as pd

from .excel import load_data
from ..data.repository import Repository
from ..schemas.schedule import ScheduleRow

MONTHS_RU = [
    "ЯНВАРЬ",
    "ФЕВРАЛЬ",
    "МАРТ",
    "АПРЕЛЬ",
    "МАЙ",
    "ИЮНЬ",
    "ИЮЛЬ",
    "АВГУСТ",
    "СЕНТЯБРЬ",
    "ОКТЯБРЬ",
    "НОЯБРЬ",
    "ДЕКАБРЬ",
]

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

    def __init__(self, repo: Repository | None = None) -> None:
        self._repo = repo or Repository()
        self._cache: Dict[str, pd.DataFrame | None] = {}

    def _load_month(self, month: str) -> pd.DataFrame | None:
        month = month.upper()
        if month in self._cache:
            return self._cache[month]
        df = load_data(sheet_name=month)
        if df is not None:
            df = df.copy()
        self._cache[month] = df
        return df

    async def get_schedule_by_day(self, date_str: str) -> List[ScheduleRow]:
        try:
            day_date = date.fromisoformat(date_str)
        except Exception:
            return []
        month_name = MONTHS_RU[day_date.month - 1]
        df = self._load_month(month_name)
        result: List[ScheduleRow] = []
        point_map = {v: k for k, v in POINTS.items()}
        if df is None:
            for code, name in POINTS.items():
                result.append(ScheduleRow(point=name, short=code))
            return result
        df = df.reset_index(drop=True)
        if df.shape[0] < 2:
            return result
        header = df.iloc[0].tolist()
        df.columns = header
        df = df.drop([0, 1]).reset_index(drop=True)
        day_col = str(day_date.day)
        if day_col not in df.columns:
            for code, name in POINTS.items():
                result.append(ScheduleRow(point=name, short=code))
            return result
        name_col = "ИМЯ" if "ИМЯ" in df.columns else df.columns[0]
        name_map = {}
        for e in self._repo.list_employees():
            name_map[e.name] = e.id
            name_map[e.full_name] = e.id
        assign: Dict[str, ScheduleRow] = {}
        for _, row in df.iterrows():
            raw_name = str(row.get(name_col, "")).strip()
            if not raw_name:
                continue
            code = str(row.get(day_col, "")).strip()
            if not code:
                continue
            point_full = POINTS.get(code)
            if not point_full:
                if code in point_map:
                    point_full = code
                    code = point_map[code]
                else:
                    continue
            if code not in assign:
                assign[code] = ScheduleRow(
                    point=point_full,
                    short=code,
                    employee_id=name_map.get(raw_name, ""),
                    name=raw_name,
                )
        for code, name in POINTS.items():
            result.append(assign.get(code, ScheduleRow(point=name, short=code)))
        return result
