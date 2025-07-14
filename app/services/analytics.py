from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from ..config import EXCEL_FILE, SALES_FILE
from ..core.constants import MONTHS_RU
from ..utils.logger import log


class AnalyticsService:
    """Load sales analytics from the salary Excel workbook."""

    def __init__(self) -> None:
        self._data: Optional[dict] = None
        self._updated_at: Optional[datetime] = None

    def _collect_sales(self) -> dict:
        try:
            xls = pd.ExcelFile(EXCEL_FILE)
        except Exception as exc:
            log(f"❌ Failed to read Excel: {exc}")
            return {
                "repair_sum": 0,
                "repair_count": 0,
                "cosmetics_sum": 0,
                "cosmetics_count": 0,
                "updated_at": datetime.utcnow().isoformat(),
            }

        repair_sum = repair_count = 0
        cosmetics_sum = cosmetics_count = 0
        months = [m.upper() for m in MONTHS_RU]
        for sheet in xls.sheet_names:
            name = sheet.split()[0].upper()
            if name not in months:
                continue
            try:
                df = pd.read_excel(xls, sheet_name=sheet, header=1)
            except Exception:
                continue
            cols = {str(c).strip(): c for c in df.columns}
            if "Ремонт" in cols:
                col = cols["Ремонт"]
                series = pd.to_numeric(df[col], errors="coerce").fillna(0)
                repair_sum += series.sum()
                repair_count += (series != 0).sum()
            if "Косметика" in cols:
                col = cols["Косметика"]
                series = pd.to_numeric(df[col], errors="coerce").fillna(0)
                cosmetics_sum += series.sum()
                cosmetics_count += (series != 0).sum()

        self._updated_at = datetime.utcnow()
        data = {
            "repair_sum": int(repair_sum),
            "repair_count": int(repair_count),
            "cosmetics_sum": int(cosmetics_sum),
            "cosmetics_count": int(cosmetics_count),
            "updated_at": self._updated_at.isoformat(),
        }
        self._data = data
        return data

    async def get_sales(self) -> dict:
        if self._data is None:
            return self._collect_sales()
        return self._data

    async def refresh_sales(self) -> dict:
        return self._collect_sales()

    def _load_sales_details(self) -> pd.DataFrame | None:
        try:
            df = pd.read_excel(
                SALES_FILE,
                header=None,
                usecols="A,B,E,G,I",
                names=["period", "order_number", "employee", "item", "cost"],
            )
            df["cost"] = pd.to_numeric(df["cost"], errors="coerce").fillna(0)
            df.dropna(how="all", inplace=True)
            return df
        except Exception as exc:
            log(f"❌ Failed to read sales details: {exc}")
            return None

    async def get_sales_details(self, period: str | None = None) -> dict:
        df = self._load_sales_details()
        if df is None:
            return {"items": [], "total": 0, "count": 0, "avg": 0}
        if period:
            df = df[df["period"].astype(str) == str(period)]
        total = int(df["cost"].sum())
        count = int(len(df))
        avg = float(total / count) if count else 0.0
        return {
            "items": df.to_dict(orient="records"),
            "total": total,
            "count": count,
            "avg": avg,
        }
