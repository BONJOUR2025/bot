"""API endpoints for master works dashboard."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query


def create_masters_router() -> APIRouter:
    router = APIRouter(prefix="/masters", tags=["Masters"])

    @router.get("/works")
    async def get_works(
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
    ):
        """Return aggregated service works with warnings and salary summary."""
        from app.services.masters_service import fetch_works, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Firebird недоступен: драйвер fdb не установлен.",
            )

        try:
            result = fetch_works(date_from=date_from, date_to=date_to)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        return result

    return router
