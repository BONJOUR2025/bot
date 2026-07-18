"""API endpoint for the "Настройки Agbis" admin page."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from .dependencies import require_permission


def create_agbis_settings_router() -> APIRouter:
    router = APIRouter(
        prefix="/agbis-settings",
        tags=["Agbis Settings"],
        dependencies=[Depends(require_permission("payroll"))],
    )

    @router.get("/")
    async def get_settings_matrix():
        """Every Agbis LOCAL_OPTION, grouped and compared across all POS computers."""
        from app.services.agbis_settings_service import get_agbis_settings_matrix
        from app.services.firebird_service import run_with_timeout, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")
        try:
            return await run_with_timeout(get_agbis_settings_matrix)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return router
