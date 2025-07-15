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

        self._details_df = df
        self._details_mtime = mtime
        elapsed = (datetime.utcnow() - start).total_seconds()
        log(f"✅ Loaded {len(df)} sales details in {elapsed:.2f}s")
        return df

    async def _firebird_details(
        self,
        period: str | None,
        period_from: str | None,
        period_to: str | None,
        creator_ids: list[str] | None,
        user_ids: list[str] | None,
        folder_ids: list[str],
        item_code: str | None,
        item_name: str | None,
        min_cost: float | None,
        max_cost: float | None,
        doc_number: str | None,
        page: int,
        page_size: int,
    ) -> dict | None:
        if not self._fb:
            return None

        filters = []
        params: list[Any] = []
        if period:
            filters.append("doc_date = ?")
            params.append(period)
        if period_from:
            filters.append("doc_date >= ?")
            params.append(period_from)
        if period_to:
            filters.append("doc_date <= ?")
            params.append(period_to)
        if creator_ids:
            placeholders = ",".join(["?"] * len(creator_ids))
            filters.append(f"creator_id IN ({placeholders})")
            params.extend(creator_ids)
        if user_ids:
            placeholders = ",".join(["?"] * len(user_ids))
            filters.append(f"user_id IN ({placeholders})")
            params.extend(user_ids)
        if folder_ids:
            placeholders = ",".join(["?"] * len(folder_ids))
            filters.append(f"folder_id IN ({placeholders})")
            params.extend(folder_ids)
        if item_code:
            filters.append("item_code CONTAINING ?")
            params.append(item_code)
        if item_name:
            filters.append("item_name CONTAINING ?")
            params.append(item_name)
        if min_cost is not None:
            filters.append("kredit >= ?")
            params.append(min_cost)
        if max_cost is not None:
            filters.append("kredit <= ?")
            params.append(max_cost)
        if doc_number:
            filters.append("doc_number CONTAINING ?")
            params.append(doc_number)

        where_clause = " AND ".join(filters)
        if where_clause:
            where_clause = "WHERE " + where_clause

        fb_version = self._fb.get_version()
        offset_supported = False
        try:
            if fb_version and int(fb_version.split(".")[0]) >= 3:
                offset_supported = True
        except Exception:
            offset_supported = False

        if offset_supported:
            query = (
                "SELECT doc_date, doc_number, creator_id, user_id, item_code, item_name, kredit "
                "FROM SALES "
                f"{where_clause} ORDER BY doc_date, doc_number OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
            )
        else:
            query = (
                "SELECT doc_date, doc_number, creator_id, user_id, item_code, item_name, kredit "
                "FROM SALES "
                f"{where_clause} ORDER BY doc_date, doc_number ROWS ? TO ?"
            )

        count_query = f"SELECT COUNT(*) as cnt FROM SALES {where_clause}"

        key = (
            tuple(params),
            page,
            page_size,
        )

        if offset_supported:
            params_with_pagination = params + [max(0, (page - 1) * page_size), page_size]
        else:
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
        period: str | None = None,
        period_from: str | None = None,
        period_to: str | None = None,
        creator_ids: list[str] | None = None,
        user_ids: list[str] | None = None,
        folder_ids: list[str] | None = None,
        item_code: str | None = None,
        employee: str | None = None,
        item: str | None = None,
        min_cost: float | None = None,
        max_cost: float | None = None,
        doc_number: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        if self._fb:
            return await self._firebird_details(
                period,
                period_from,
                period_to,
                creator_ids or [],
                user_ids or [],
                folder_ids or [],
                item_code,
                item,
                min_cost,
                max_cost,
                doc_number,
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
        if period:
            dt = pd.to_datetime(period, errors="coerce", dayfirst=True)
            if not pd.isna(dt):
                filtered = filtered[filtered["period"] == dt]
            else:
                filtered = filtered.iloc[0:0]

        if period_from:
            dt_from = pd.to_datetime(period_from, errors="coerce", dayfirst=True)
            if not pd.isna(dt_from):
                filtered = filtered[filtered["period"] >= dt_from]

        if period_to:
            dt_to = pd.to_datetime(period_to, errors="coerce", dayfirst=True)
            if not pd.isna(dt_to):
                filtered = filtered[filtered["period"] <= dt_to]

        if employee:
            filtered = filtered[
                filtered["employee"]
                .astype(str)
                .str.contains(employee, case=False, na=False)
            ]

        if item:
            filtered = filtered[
                filtered["item"].astype(str).str.contains(item, case=False, na=False)
            ]

        if min_cost is not None:
            filtered = filtered[filtered["cost"] >= float(min_cost)]

        if max_cost is not None:
            filtered = filtered[filtered["cost"] <= float(max_cost)]

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
