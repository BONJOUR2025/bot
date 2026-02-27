"""API endpoints for payroll calculation."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.payroll_service import PayrollService, get_payroll_service, make_month_key
from app.data.sales_plans_repository import SalesPlansRepository, get_sales_plans_repository
from app.data.payroll_settlement_repository import get_payroll_settlement_repository
from app.services.access_control_service import AccessControlService, ResolvedUser
from .dependencies import get_current_user


class SalesPlanInput(BaseModel):
    employee_code: str
    employee_name: str
    month_key: str | None = None
    repair_plan: float | None = None
    cosmetics_plan: float | None = None
    shoes_plan: float | None = None
    ignore_kpi: bool | None = None
    force_max: list = []
    force_min: list = []


class SalesPlanOutput(BaseModel):
    employee_code: str
    employee_name: str
    month_key: str | None = None
    repair_plan: float
    cosmetics_plan: float
    shoes_plan: float
    ignore_kpi: bool
    force_max: list = []
    force_min: list = []


class PayrollRowOutput(BaseModel):
    employee_code: str
    employee_name: str
    base_salary: float
    repair_sales: float
    cosmetics_sales: float
    shoes_sales: float
    repair_plan: float
    cosmetics_plan: float
    shoes_plan: float
    repair_fulfillment: float
    cosmetics_fulfillment: float
    shoes_fulfillment: float
    repair_rate: float
    cosmetics_rate: float
    shoes_rate: float
    repair_commission: float
    cosmetics_commission: float
    shoes_commission: float
    bonuses: float
    excel_bonus: float
    penalties: float
    advances: float
    advances_this_month: float = 0.0
    ignore_kpi: bool
    force_max: list = []
    force_min: list = []
    shoes_orders: list[str]
    total_commission: float
    total_gross: float
    total_deductions: float
    total_net: float
    settlement_paid: bool = False


class SettlementInput(BaseModel):
    paid: bool


def create_payroll_router(
    payroll_service: PayrollService | None = None,
    plans_repo: SalesPlansRepository | None = None,
    access_service: AccessControlService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/payroll", tags=["Payroll"])

    _payroll = payroll_service or get_payroll_service()
    _plans = plans_repo or get_sales_plans_repository()
    _settlements = get_payroll_settlement_repository()

    def _check(current: ResolvedUser) -> None:
        if access_service and not access_service.user_has_permission(current, "payroll"):
            raise HTTPException(status_code=403, detail="forbidden")

    # ── Months ────────────────────────────────────────────────────
    @router.get("/months", response_model=list[str])
    async def list_months(current: ResolvedUser = Depends(get_current_user)):
        _check(current)
        return _payroll.list_months()

    # ── Calculate ─────────────────────────────────────────────────
    @router.get("/calculate", response_model=list[PayrollRowOutput])
    async def calculate_payroll(
        month: str = Query(...),
        year: Optional[int] = Query(None),
        current: ResolvedUser = Depends(get_current_user),
    ):
        _check(current)
        rows = await _payroll.calculate_payroll(month, year)
        return [PayrollRowOutput(**row.to_dict()) for row in rows]

    @router.get("/calculate/{employee_code}", response_model=PayrollRowOutput | None)
    async def get_employee_payroll(
        employee_code: str,
        month: str = Query(...),
        year: Optional[int] = Query(None),
        current: ResolvedUser = Depends(get_current_user),
    ):
        _check(current)
        row = await _payroll.get_employee_details(employee_code, month, year)
        return PayrollRowOutput(**row.to_dict()) if row else None

    # ── Advances history ──────────────────────────────────────────
    @router.get("/advances-history")
    async def advances_history(
        month: str = Query(...),
        year: int = Query(...),
        current: ResolvedUser = Depends(get_current_user),
    ):
        _check(current)
        return _payroll.get_advances_history(month, year)

    # ── Settlements ───────────────────────────────────────────────
    @router.get("/settlements")
    async def get_settlements(
        month: str = Query(...),
        year: int = Query(...),
        current: ResolvedUser = Depends(get_current_user),
    ):
        _check(current)
        return _settlements.get_settlements_map(make_month_key(month, year))

    @router.put("/settlements/{employee_code}")
    async def set_settlement(
        employee_code: str,
        data: SettlementInput,
        month: str = Query(...),
        year: int = Query(...),
        current: ResolvedUser = Depends(get_current_user),
    ):
        _check(current)
        return _settlements.set_settlement(make_month_key(month, year), employee_code, data.paid)

    # ── Plans ─────────────────────────────────────────────────────
    @router.get("/plans", response_model=list[SalesPlanOutput])
    async def list_plans(
        month: Optional[str] = Query(None),
        year: Optional[int] = Query(None),
        current: ResolvedUser = Depends(get_current_user),
    ):
        _check(current)
        if month and year:
            mk = make_month_key(month, year)
            month_plans = _plans.list_plans(month_key=mk)
            month_codes = {p.employee_code for p in month_plans}
            # Include global plans not overridden by month-specific ones
            global_plans = [
                p for p in _plans.list_plans(month_key=None)
                if p.month_key is None and p.employee_code not in month_codes
            ]
            all_plans = month_plans + global_plans
        else:
            all_plans = _plans.list_plans()

        return [
            SalesPlanOutput(
                employee_code=p.employee_code,
                employee_name=p.employee_name,
                month_key=p.month_key,
                repair_plan=p.repair_plan,
                cosmetics_plan=p.cosmetics_plan,
                shoes_plan=p.shoes_plan,
                ignore_kpi=p.ignore_kpi,
                force_max=p.force_max,
                force_min=p.force_min,
            )
            for p in all_plans
        ]

    @router.get("/plans/{employee_code}", response_model=SalesPlanOutput | None)
    async def get_plan(
        employee_code: str,
        month: Optional[str] = Query(None),
        year: Optional[int] = Query(None),
        current: ResolvedUser = Depends(get_current_user),
    ):
        _check(current)
        mk = make_month_key(month, year) if month and year else None
        plan = _plans.get_plan(employee_code, month_key=mk)
        if not plan:
            return None
        return SalesPlanOutput(
            employee_code=plan.employee_code,
            employee_name=plan.employee_name,
            month_key=plan.month_key,
            repair_plan=plan.repair_plan,
            cosmetics_plan=plan.cosmetics_plan,
            shoes_plan=plan.shoes_plan,
            ignore_kpi=plan.ignore_kpi,
            force_max=plan.force_max,
            force_min=plan.force_min,
        )

    @router.put("/plans", response_model=SalesPlanOutput)
    async def set_plan(
        data: SalesPlanInput,
        current: ResolvedUser = Depends(get_current_user),
    ):
        _check(current)
        plan = _plans.set_plan(
            employee_code=data.employee_code,
            employee_name=data.employee_name,
            month_key=data.month_key,
            repair_plan=data.repair_plan,
            cosmetics_plan=data.cosmetics_plan,
            shoes_plan=data.shoes_plan,
            ignore_kpi=data.ignore_kpi,
            force_max=data.force_max,
            force_min=data.force_min,
        )
        return SalesPlanOutput(
            employee_code=plan.employee_code,
            employee_name=plan.employee_name,
            month_key=plan.month_key,
            repair_plan=plan.repair_plan,
            cosmetics_plan=plan.cosmetics_plan,
            shoes_plan=plan.shoes_plan,
            ignore_kpi=plan.ignore_kpi,
            force_max=plan.force_max,
            force_min=plan.force_min,
        )

    @router.delete("/plans/{employee_code}")
    async def delete_plan(
        employee_code: str,
        month: Optional[str] = Query(None),
        year: Optional[int] = Query(None),
        current: ResolvedUser = Depends(get_current_user),
    ):
        _check(current)
        mk = make_month_key(month, year) if month and year else None
        if not _plans.delete_plan(employee_code, month_key=mk):
            raise HTTPException(status_code=404, detail="Plan not found")
        return {"status": "deleted"}

    return router
