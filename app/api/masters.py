"""API endpoints for master works dashboard."""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .dependencies import require_permission


def create_masters_router() -> APIRouter:
    router = APIRouter(
        prefix="/masters",
        tags=["Masters"],
        dependencies=[Depends(require_permission("payroll"))],
    )

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
            # fetch_works is unbounded (no SQL row cap, no per-request
            # deadline) and this endpoint sits behind xtunnel, which has
            # documented relay-side instability with long-lived connections
            # (see xtunnel_healthcheck.py) — a request left to hang
            # indefinitely surfaces to the browser as a bare "Network
            # Error" with no explanation. Bounding it here at least turns
            # that into an actionable message; the thread itself can't be
            # killed (Python threads aren't cancellable), it just keeps
            # running server-side after the response goes out.
            result = await asyncio.wait_for(
                asyncio.to_thread(fetch_works, date_from=date_from, date_to=date_to),
                timeout=55,
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Запрос выполняется слишком долго. Выберите период покороче (например, один месяц) и попробуйте снова.",
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        return result

    return router
