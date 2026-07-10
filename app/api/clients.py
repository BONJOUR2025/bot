"""API endpoints for the client CRM view (Agbis contragents)."""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .dependencies import require_permission


def create_clients_router() -> APIRouter:
    router = APIRouter(
        prefix="/clients",
        tags=["Clients"],
        dependencies=[Depends(require_permission("payroll"))],
    )

    @router.get("/search")
    async def search_clients(q: str = Query(..., min_length=2)):
        """Search Agbis clients by name or phone."""
        from app.services.firebird_service import get_firebird_service, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")

        try:
            svc = get_firebird_service()
            return await asyncio.to_thread(svc.search_clients, q)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/churning")
    async def get_churning_clients(
        lookback_days: int = Query(default=365, ge=30, le=1095),
        min_orders: int = Query(default=3, ge=2, le=50),
    ):
        """Return clients who used to order regularly and have gone quiet."""
        from app.services.firebird_service import get_firebird_service, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")

        try:
            svc = get_firebird_service()
            return await asyncio.to_thread(svc.get_churning_clients, lookback_days, min_orders)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/{contragent_id}/orders/{doc_num}/items")
    async def get_order_items(contragent_id: int, doc_num: str):
        """Return the services/goods inside one client order."""
        from app.services.firebird_service import get_firebird_service, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")

        try:
            svc = get_firebird_service()
            return await asyncio.to_thread(svc.get_order_items, contragent_id, doc_num)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/{contragent_id}")
    async def get_client_profile(contragent_id: int):
        """Return one client's full order history, LTV, average check, last visit."""
        from app.services.firebird_service import get_firebird_service, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")

        try:
            svc = get_firebird_service()
            profile = await asyncio.to_thread(svc.get_client_profile, contragent_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        if profile is None:
            raise HTTPException(status_code=404, detail="Клиент не найден")
        return profile

    return router
