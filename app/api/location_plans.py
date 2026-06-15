from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import require_permission
from app.data.location_repository import LocationRepository
from app.schemas.location_plan import (
    LocationCode, LocationPlan, LocationPlanUpsert,
)


def create_location_plans_router(repo: LocationRepository) -> APIRouter:
    router = APIRouter(prefix="/location-plans", tags=["LocationPlans"])

    # ── Location codes (read-only, derived from «Салоны») ─────────

    @router.get("/codes", response_model=list[LocationCode])
    async def list_codes(current=Depends(require_permission("payroll"))):
        return repo.list_codes()

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
