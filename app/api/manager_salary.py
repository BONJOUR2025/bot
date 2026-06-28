"""API for manager salary (оклад + KPI), accruals and advance deduction."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.services.payout_service import PayoutService
from app.services.access_control_service import AccessControlService, ResolvedUser
from app.services.manager_salary import calc_manager_salary
from app.data.manager_salary_repository import get_manager_salary_repository

from .dependencies import get_current_user, require_permission

MANAGER_SALARY_PERMISSION = "manager-salary"
ADVANCE_TYPE = "Аванс"


class SalaryInput(BaseModel):
    oklad: float = 0
    kpi_max: float = 0
    w_revenue: float = 0.35
    w_repair: float = 0.20
    w_sew: float = 0.20
    revenue_plan: float = 0
    revenue_actual: float = 0
    repair_plan_conv: float = 0.50
    repair_target_deals: int = 0
    repair_total_deals: int = 0
    sew_plan_conv: float = 0.25
    sew_target_deals: int = 0
    sew_total_deals: int = 0
    sew_new_leads: int = 0
    sew_min_leads: int = 50
    advances: float = 0


class AccrualInput(SalaryInput):
    employee_code: str = ""
    employee_name: str = ""
    user_id: str = ""
    period: str = ""          # e.g. "2026-06"
    date_from: str = ""
    date_to: str = ""


def _calc(data: SalaryInput) -> dict:
    return calc_manager_salary(
        oklad=data.oklad, kpi_max=data.kpi_max,
        w_revenue=data.w_revenue, w_repair=data.w_repair, w_sew=data.w_sew,
        revenue_plan=data.revenue_plan, revenue_actual=data.revenue_actual,
        repair_plan_conv=data.repair_plan_conv,
        repair_target_deals=data.repair_target_deals,
        repair_total_deals=data.repair_total_deals,
        sew_plan_conv=data.sew_plan_conv,
        sew_target_deals=data.sew_target_deals,
        sew_total_deals=data.sew_total_deals,
        sew_new_leads=data.sew_new_leads, sew_min_leads=data.sew_min_leads,
        advances=data.advances,
    )


def create_manager_salary_router(
    payout_service: PayoutService, access_service: AccessControlService
) -> APIRouter:
    router = APIRouter(prefix="/manager-salary", tags=["ManagerSalary"])

    @router.post("/calc")
    async def calc(
        data: SalaryInput,
        current: ResolvedUser = Depends(require_permission(MANAGER_SALARY_PERMISSION)),
    ):
        """Authoritative salary calculation (no persistence)."""
        return _calc(data)

    @router.get("/advances")
    async def advances(
        employee_id: str = Query(...),
        date_from: str = Query(...),
        date_to: str = Query(...),
        current: ResolvedUser = Depends(require_permission(MANAGER_SALARY_PERMISSION)),
    ):
        """Sum of advances (выплаты типа «Аванс») issued to the employee in the
        period — used as the deduction from the accrued salary."""
        rows = await payout_service.list_payouts(
            employee_id=employee_id, payout_type=ADVANCE_TYPE,
            from_date=date_from, to_date=date_to,
        )
        total = round(sum(float(p.amount or 0) for p in rows), 2)
        return {"total": total, "count": len(rows),
                "items": [{"id": p.id, "amount": p.amount, "status": p.status,
                           "timestamp": str(p.timestamp) if p.timestamp else None} for p in rows]}

    @router.post("/accrue")
    async def accrue(
        data: AccrualInput,
        current: ResolvedUser = Depends(require_permission(MANAGER_SALARY_PERMISSION)),
    ):
        """Recompute server-side and store the accrual with its full breakdown."""
        result = _calc(data)
        entry = get_manager_salary_repository().add({
            "employee_code": data.employee_code,
            "employee_name": data.employee_name,
            "user_id": data.user_id,
            "period": data.period,
            "date_from": data.date_from,
            "date_to": data.date_to,
            "actor": getattr(current, "login", None) or getattr(current, "id", None),
            "inputs": data.model_dump(),
            "result": result,
        })
        return entry

    @router.get("/accruals")
    async def accruals(
        employee_code: Optional[str] = None,
        period: Optional[str] = None,
        limit: int = 200,
        current: ResolvedUser = Depends(require_permission(MANAGER_SALARY_PERMISSION)),
    ):
        return get_manager_salary_repository().list(
            employee_code=employee_code, period=period, limit=limit)

    @router.delete("/accruals/{accrual_id}")
    async def delete_accrual(
        accrual_id: int,
        current: ResolvedUser = Depends(require_permission(MANAGER_SALARY_PERMISSION)),
    ):
        return {"deleted": get_manager_salary_repository().delete(accrual_id)}

    return router
