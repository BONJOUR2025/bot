"""API endpoint for the Пользователи АГБИС admin page."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from .dependencies import require_permission


def create_agbis_users_router() -> APIRouter:
    router = APIRouter(
        prefix="/agbis-users",
        tags=["Agbis Users"],
        dependencies=[Depends(require_permission("payroll"))],
    )

    @router.get("/")
    async def list_agbis_users():
        """Return all Agbis USERS rows with role/department info."""
        from app.services.firebird_service import get_firebird_service, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")
        try:
            return await asyncio.to_thread(get_firebird_service().get_agbis_users)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return router
