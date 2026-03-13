"""API endpoints for sales analytics dashboard."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query


def create_sales_router() -> APIRouter:
    router = APIRouter(prefix="/sales", tags=["Sales"])

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

    return router
