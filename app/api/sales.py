"""API endpoints for sales analytics dashboard."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .dependencies import require_permission


def create_sales_router() -> APIRouter:
    router = APIRouter(
        prefix="/sales",
        tags=["Sales"],
        dependencies=[Depends(require_permission("payroll"))],
    )

    @router.get("/daily")
    async def get_daily_sales(
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
    ):
        """Return daily repair + cosmetics sales by employee for a date range."""
        from app.services.firebird_service import get_firebird_service, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Firebird недоступен: драйвер fdb не установлен.",
            )

        today = date.today()
        df = date_from or (today - timedelta(days=30))
        dt = date_to or today

        if df > dt:
            raise HTTPException(status_code=400, detail="date_from не может быть позже date_to")

        try:
            svc = get_firebird_service()
            rows = svc.get_daily_sales(df, dt)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        return rows

    @router.get("/client-retention")
    async def get_client_retention(
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
    ):
        """Return new-vs-returning client counts for a date range."""
        from app.services.firebird_service import get_firebird_service, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Firebird недоступен: драйвер fdb не установлен.",
            )

        today = date.today()
        df = date_from or (today - timedelta(days=30))
        dt = date_to or today

        if df > dt:
            raise HTTPException(status_code=400, detail="date_from не может быть позже date_to")

        try:
            svc = get_firebird_service()
            return svc.get_client_retention(df, dt)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/plans")
    async def get_plans(month_keys: Optional[str] = Query(default=None)):
        """Return sales plans keyed by month_key → employee_code → {repair_plan, cosmetics_plan, shoes_plan}.

        month_keys: comma-separated list of month keys like ЯНВАРЬ_2025,ФЕВРАЛЬ_2025
        """
        from app.data.sales_plans_repository import get_sales_plans_repository

        repo = get_sales_plans_repository()
        if not month_keys:
            return {}

        keys = [k.strip() for k in month_keys.split(',') if k.strip()]
        result: dict = {}
        for key in keys:
            plans_map = repo.get_plans_map(month_key=key)
            result[key] = {
                code: {
                    "repair_plan":    p.repair_plan,
                    "cosmetics_plan": p.cosmetics_plan,
                    "shoes_plan":     p.shoes_plan,
                }
                for code, p in plans_map.items()
            }
        return result

    return router
