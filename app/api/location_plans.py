from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import require_permission
from app.data.location_repository import LocationRepository
from app.schemas.location_plan import (
    LocationCode, LocationCodeCreate, LocationCodeUpdate,
    LocationPlan, LocationPlanUpsert,
)


def create_location_plans_router(repo: LocationRepository) -> APIRouter:
    router = APIRouter(prefix="/location-plans", tags=["LocationPlans"])

    # ── Location codes ────────────────────────────────────────────

    @router.get("/codes", response_model=list[LocationCode])
    async def list_codes(current=Depends(require_permission("payroll"))):
        return repo.list_codes()

    @router.post("/codes", response_model=LocationCode)
    async def create_code(
        data: LocationCodeCreate,
        current=Depends(require_permission("payroll")),
    ):
        if repo.get_code(data.code):
            raise HTTPException(status_code=400, detail="code_exists")
        return repo.upsert_code(data.code, data.name, data.sort_order)

    @router.patch("/codes/{code}", response_model=LocationCode)
    async def update_code(
        code: str,
        data: LocationCodeUpdate,
        current=Depends(require_permission("payroll")),
    ):
        existing = repo.get_code(code)
        if not existing:
            raise HTTPException(status_code=404, detail="not_found")
        return repo.upsert_code(
            code,
            data.name if data.name is not None else existing.name,
            data.sort_order if data.sort_order is not None else existing.sort_order,
        )

    @router.delete("/codes/{code}")
    async def delete_code(
        code: str,
        current=Depends(require_permission("payroll")),
    ):
        if not repo.delete_code(code):
            raise HTTPException(status_code=404, detail="not_found")
        return {"status": "deleted"}

    # ── Monthly plans ─────────────────────────────────────────────

    @router.get("/plans", response_model=list[LocationPlan])
    async def list_plans(
        month_key: str = Query(...),
        current=Depends(require_permission("payroll")),
    ):
        return repo.list_plans(month_key)

    @router.put("/plans", response_model=LocationPlan)
    async def upsert_plan(
        data: LocationPlanUpsert,
        current=Depends(require_permission("payroll")),
    ):
        return repo.upsert_plan(
            location_code=data.location_code,
            month_key=data.month_key,
            repair_plan=data.repair_plan,
            cosmetics_plan=data.cosmetics_plan,
            shoes_plan=data.shoes_plan,
        )

    # ── Combined: codes + plans for a month (for frontend convenience) ──

    @router.get("/full")
    async def get_full(
        month_key: str = Query(...),
        current=Depends(require_permission("payroll")),
    ):
        codes = repo.list_codes()
        plans = {p.location_code: p for p in repo.list_plans(month_key)}
        return {
            "codes": [c.dict() for c in codes],
            "plans": {
                code.code: plans.get(code.code, LocationPlan(
                    location_code=code.code,
                    month_key=month_key,
                )).dict()
                for code in codes
            },
        }

    return router
