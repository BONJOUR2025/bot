from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Any, List
import asyncio
import os

import pandas as pd

from ..config import (
    EXCEL_FILE,
    SALES_FILE,
    FIREBIRD_DB,
    FIREBIRD_USER,
    FIREBIRD_PASSWORD,
)
from .firebird_service import FirebirdService
from ..core.constants import MONTHS_RU
from ..utils.logger import log
import re

# Mapping of 4 digit codes to employee names used in sales analytics
EMPLOYEE_CODE_MAP = {
    "0102": "Вера 0102",
    "2602": "Анастасия 2602",
    "7272": "Арина 7272",
    "1505": "Александр 1505",
    "2404": "Эмиль 2404",
    "5984": "Полина 5984",
    "0704": "Наталья 0704",
    "2201": "Катя 2201",
    "1606": "Лали 1606",
    "0104": "Екатерина 0104",
    "2006": "Ира 2405",
    "1802": "Полина 1802",
    "1996": "Вероника 1996",
    "2405": "Ирина 2405",
    "3007": "Юля 3007",
    "2104": "Алекс 2104",
    "0208": "Марина 0208",
}


def map_employee_by_code(description: str | None) -> str:
    """Return employee name by the last 4 digits in the description."""
    if not description:
        return description or ""
    match = re.search(r"(\d{4})\s*$", str(description))
    if match:
        code = match.group(1)
        return EMPLOYEE_CODE_MAP.get(code, str(description))
    return str(description)


class AnalyticsService:
    """Load sales analytics from the salary Excel workbook."""

    def __init__(self, fb_service: FirebirdService | None = None) -> None:
        self._data: Optional[dict] = None
        self._updated_at: Optional[datetime] = None
        self._details_df: Optional[pd.DataFrame] = None
        self._details_mtime: float = 0.0
        if fb_service:
            self._fb = fb_service
        elif FIREBIRD_DB and FIREBIRD_USER and FIREBIRD_PASSWORD:
            self._fb = FirebirdService(FIREBIRD_DB, FIREBIRD_USER, FIREBIRD_PASSWORD)
        else:
            self._fb = None

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

    async def refresh_sales_details(self) -> None:
        """Force refresh cached sales details."""
        await self._ensure_details_df(force=True)

    async def _read_sales_file(self) -> pd.DataFrame:
        def _read() -> pd.DataFrame:
            return pd.read_excel(
                SALES_FILE,
                header=None,
                usecols="A,B,E,G,I",
                names=["period", "order_number", "employee", "item", "cost"],
            )

        return await asyncio.to_thread(_read)

    async def _ensure_details_df(self, force: bool = False) -> pd.DataFrame | None:
        try:
            mtime = os.path.getmtime(SALES_FILE)
        except Exception as exc:
            log(f"❌ Failed to stat sales file: {exc}")
            return None

        if self._details_df is not None and not force and mtime == self._details_mtime:
            return self._details_df

        start = datetime.utcnow()
        try:
            df = await self._read_sales_file()
        except Exception as exc:
            log(f"❌ Failed to read sales details: {exc}")
            return None

        df.columns = ["period", "order_number", "employee", "item", "cost"]
        df.dropna(how="all", inplace=True)
        df["cost"] = pd.to_numeric(df["cost"], errors="coerce").fillna(0)
        df["order_number"] = df["order_number"].astype(str).str.strip()
        df = df[
            df["order_number"].notna()
            & (df["order_number"] != "")
            & (df["order_number"].str.lower() != "nan")
        ]
        df["period"] = pd.to_datetime(df["period"], errors="coerce", dayfirst=True)
        dropped = df["period"].isna().sum()
        if dropped:
            log(f"⚠️ Dropped {dropped} rows with invalid period")
        df = df.dropna(subset=["period"]).reset_index(drop=True)

        # Replace employee field with mapped name if possible
        df["employee"] = df["employee"].apply(map_employee_by_code)

        self._details_df = df
        self._details_mtime = mtime
        elapsed = (datetime.utcnow() - start).total_seconds()
        log(f"✅ Loaded {len(df)} sales details in {elapsed:.2f}s")
        return df

    async def _firebird_details(
        self,
        date_from: str | None,
        date_to: str | None,
        creater_ids: list[str] | None,
        user_ids: list[str] | None,
        folder_ids: list[str],
        code_substr: str | None,
        name_substr: str | None,
        min_kredit: float | None,
        max_kredit: float | None,
        doc_num_substr: str | None,
        page: int,
        page_size: int,
    ) -> dict | None:
        if not self._fb:
            return None

        filters = ["docs_order_history.status_id = 5"]
        params: list[Any] = []
        if date_from:
            filters.append("docs.doc_date >= ?")
            params.append(date_from)
        if date_to:
            filters.append("docs.doc_date <= ?")
            params.append(date_to)
        if creater_ids:
            placeholders = ",".join(["?"] * len(creater_ids))
            filters.append(f"docs_order.creater_id IN ({placeholders})")
            params.extend(creater_ids)
        if user_ids:
            placeholders = ",".join(["?"] * len(user_ids))
            filters.append(f"users.user_id IN ({placeholders})")
            params.extend(user_ids)
        if folder_ids:
            placeholders = ",".join(["?"] * len(folder_ids))
            filters.append(f"tovars_tbl.folder_id IN ({placeholders})")
            params.extend(folder_ids)
        if code_substr:
            filters.append("tovars_tbl.code CONTAINING ?")
            params.append(code_substr)
        if name_substr:
            filters.append("tovars_tbl.name CONTAINING ?")
            params.append(name_substr)
        if min_kredit is not None:
            filters.append("doc_order_lines.kredit >= ?")
            params.append(min_kredit)
        if max_kredit is not None:
            filters.append("doc_order_lines.kredit <= ?")
            params.append(max_kredit)
        if doc_num_substr:
            filters.append("docs.doc_num CONTAINING ?")
            params.append(doc_num_substr)

        where_clause = " AND ".join(filters)
        if where_clause:
            where_clause = "WHERE " + where_clause

        base_from = (
            "FROM doc_order_lines "
            "INNER JOIN docs_order ON doc_order_lines.doc_order_id = docs_order.id "
            "INNER JOIN docs_order_history ON docs_order.id = docs_order_history.doc_order_id "
            "INNER JOIN docs ON docs_order.doc_id = docs.doc_id "
            "INNER JOIN contragents ON docs.contragent_id = contragents.contr_id "
            "INNER JOIN tovars_tbl ON doc_order_lines.tovar_id = tovars_tbl.tovar_id "
            "INNER JOIN users ON docs_order.creater_id = users.user_id "
        )

        query = (
            "SELECT docs.doc_date AS doc_date, docs.doc_num AS doc_number, "
            "docs_order.creater_id AS creator_id, users.user_id AS user_id, "
            "users.description AS description, tovars_tbl.code AS item_code, "
            "tovars_tbl.name AS item_name, doc_order_lines.kredit AS kredit "
            f"{base_from} {where_clause} ORDER BY docs.doc_date, docs.doc_num ROWS ? TO ?"
        )

        count_query = f"SELECT COUNT(*) as cnt {base_from} {where_clause}"

        key = (
            tuple(params),
            page,
            page_size,
        )

        start_row = max(1, (page - 1) * page_size + 1)
        end_row = page * page_size
        params_with_pagination = params + [start_row, end_row]

        try:
            rows = await self._fb.cached_execute(key, query, params_with_pagination)
            count_rows = await self._fb.cached_execute(
                ("count", *key[0]), count_query, params
            )
        except Exception as exc:
            log(f"❌ Firebird query failed: {exc}")
            return None

        # Normalize employee descriptions using the 4 digit code map
        for row in rows:
            row["description"] = map_employee_by_code(row.get("description"))

        total_count = int(count_rows[0]["cnt"]) if count_rows else 0
        total_pages = int((total_count + page_size - 1) / page_size)

        log(f"🔎 Firebird {total_count} records (page {page}/{total_pages})")

        return {
            "items": rows,
            "total": sum(int(r.get("kredit") or 0) for r in rows),
            "count": total_count,
            "avg": (
                float(sum(int(r.get("kredit") or 0) for r in rows) / len(rows))
                if rows
                else 0
            ),
            "page": page,
            "pages": total_pages,
        }

    async def get_sales_details(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        creater_ids: list[str] | None = None,
        user_ids: list[str] | None = None,
        folder_ids: list[str] | None = None,
        code_substr: str | None = None,
        name_substr: str | None = None,
        min_kredit: float | None = None,
        max_kredit: float | None = None,
        doc_num_substr: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        if self._fb:
            return await self._firebird_details(
                date_from,
                date_to,
                creater_ids or [],
                user_ids or [],
                folder_ids or [],
                code_substr,
                name_substr,
                min_kredit,
                max_kredit,
                doc_num_substr,
                page,
                page_size,
            ) or {
                "items": [],
                "total": 0,
                "count": 0,
                "avg": 0,
                "page": page,
                "pages": 0,
            }

        df = await self._ensure_details_df()
        if df is None:
            return {
                "items": [],
                "total": 0,
                "count": 0,
                "avg": 0,
                "page": page,
                "pages": 0,
            }

        filtered = df
        if date_from:
            dt_from = pd.to_datetime(date_from, errors="coerce", dayfirst=True)
            if not pd.isna(dt_from):
                filtered = filtered[filtered["period"] >= dt_from]

        if date_to:
            dt_to = pd.to_datetime(date_to, errors="coerce", dayfirst=True)
            if not pd.isna(dt_to):
                filtered = filtered[filtered["period"] <= dt_to]

        if name_substr:
            filtered = filtered[
                filtered["item"].astype(str).str.contains(name_substr, case=False, na=False)
            ]

        if code_substr:
            filtered = filtered[
                filtered["employee"].astype(str).str.contains(code_substr, case=False, na=False)
            ]

        if doc_num_substr:
            filtered = filtered[
                filtered["order_number"].astype(str).str.contains(doc_num_substr, case=False, na=False)
            ]

        if min_kredit is not None:
            filtered = filtered[filtered["cost"] >= float(min_kredit)]

        if max_kredit is not None:
            filtered = filtered[filtered["cost"] <= float(max_kredit)]

        page_size = max(1, min(50, int(page_size)))
        page = max(1, int(page))
        total_count = int(len(filtered))
        total_pages = int((total_count + page_size - 1) / page_size)
        start = (page - 1) * page_size
        end = start + page_size
        page_df = filtered.iloc[start:end].copy()

        # format period back to string
        page_df["period"] = page_df["period"].dt.strftime("%Y-%m-%d")

        total_cost = int(filtered["cost"].sum())
        avg = float(total_cost / total_count) if total_count else 0.0

        log(f"🔎 Filtered {total_count} records (page {page}/{total_pages})")

        return {
            "items": page_df.to_dict(orient="records"),
            "total": total_cost,
            "count": total_count,
            "avg": avg,
            "page": page,
            "pages": total_pages,
        }
