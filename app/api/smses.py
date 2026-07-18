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
        from app.services.firebird_service import get_firebird_service, run_with_timeout
        svc = get_firebird_service()
        try:
            return await run_with_timeout(svc.get_smses, date_from=date_from, date_to=date_to)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Сузьте период и попробуйте снова.")

    return router
