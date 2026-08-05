import asyncio
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .dependencies import require_permission


def create_smses_router() -> APIRouter:
    router = APIRouter(prefix="/smses", tags=["smses"])
    perm = require_permission("smses")

    @router.get("/")
    async def list_smses(
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        _=Depends(perm),
    ):
        from app.services import fdb_cache
        from app.services.firebird_service import run_with_timeout
        try:
            return await run_with_timeout(fdb_cache.get_or_compute, "smses.list", (date_from, date_to))
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Сузьте период и попробуйте снова.")

    return router
