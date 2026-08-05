from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_current_user, require_permission
from app.data.salon_repository import SalonRepository
from app.schemas.salon import Salon, SalonCreate, SalonUpdate


def create_salons_router(repo: SalonRepository) -> APIRouter:
    router = APIRouter(prefix="/salons", tags=["Salons"])

    def _check(user=None):
        if user is None:
            return
        if "salons" not in user.permissions and "*" not in user.permissions:
            raise HTTPException(status_code=403, detail="forbidden")

    @router.get("/", response_model=list[Salon])
    async def list_salons(
        status: Optional[str] = Query(None),
        current=Depends(require_permission("salons")),
    ):
        return repo.list_salons(status=status)

    @router.get("/sclads")
    async def list_sclads(
        current=Depends(require_permission("salons")),
    ):
        from app.services.firebird_service import run_with_timeout
        from app.services import fdb_cache

        # Was a bare blocking call in an async handler — on a contended
        # Firebird that stalls the whole event loop, not just this request.
        try:
            return await run_with_timeout(fdb_cache.get_or_compute, "salons.sclads", ())
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Попробуйте снова чуть позже.")

    @router.get("/{salon_id}", response_model=Salon)
    async def get_salon(
        salon_id: str,
        current=Depends(require_permission("salons")),
    ):
        salon = repo.get(salon_id)
        if not salon:
            raise HTTPException(status_code=404, detail="not_found")
        return salon

    @router.post("/", response_model=Salon)
    async def create_salon(
        data: SalonCreate,
        current=Depends(require_permission("salons")),
    ):
        return repo.create(data)

    @router.patch("/{salon_id}", response_model=Salon)
    async def update_salon(
        salon_id: str,
        data: SalonUpdate,
        current=Depends(require_permission("salons")),
    ):
        salon = repo.update(salon_id, data)
        if not salon:
            raise HTTPException(status_code=404, detail="not_found")
        return salon

    @router.delete("/{salon_id}")
    async def delete_salon(
        salon_id: str,
        current=Depends(require_permission("salons")),
    ):
        if not repo.delete(salon_id):
            raise HTTPException(status_code=404, detail="not_found")
        return {"status": "deleted"}

    return router
