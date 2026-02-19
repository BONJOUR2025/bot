"""API endpoints for payroll calculation."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.payroll_service import PayrollService, get_payroll_service
from app.data.sales_plans_repository import (
    SalesPlansRepository,
    get_sales_plans_repository,
)
from app.services.access_control_service import AccessControlService, ResolvedUser
from .dependencies import get_current_user


class SalesPlanInput(BaseModel):
    """Input model for setting a sales plan."""
    employee_code: str
    employee_name: str
    repair_plan: float | None = None
    cosmetics_plan: float | None = None
    shoes_plan: float | None = None
    ignore_kpi: bool | None = None


class SalesPlanOutput(BaseModel):
    """Output model for a sales plan."""
    employee_code: str
    employee_name: str
    repair_plan: float
    cosmetics_plan: float
    shoes_plan: float
    ignore_kpi: bool


class PayrollRowOutput(BaseModel):
    """Output model for a payroll row."""
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
    ignore_kpi: bool
    shoes_orders: list[str]

    total_commission: float
    total_gross: float
    total_deductions: float
    total_net: float


def create_payroll_router(
    payroll_service: PayrollService | None = None,
    plans_repo: SalesPlansRepository | None = None,
    access_service: AccessControlService | None = None,
) -> APIRouter:
    """Create payroll API router."""
    router = APIRouter(prefix="/payroll", tags=["Payroll"])

    _payroll = payroll_service or get_payroll_service()
    _plans = plans_repo or get_sales_plans_repository()

    def _check_permission(current: ResolvedUser) -> None:
        """Check if user has payroll permission."""
        if access_service:
            if not access_service.user_has_permission(current, "payroll"):
                raise HTTPException(status_code=403, detail="forbidden")

    @router.get("/months", response_model=list[str])
    async def list_months(current: ResolvedUser = Depends(get_current_user)):
        """List available months for payroll calculation."""
        _check_permission(current)
        return _payroll.list_months()

    @router.get("/calculate", response_model=list[PayrollRowOutput])
    async def calculate_payroll(
        month: str = Query(..., description="Month name (e.g., ЯНВАРЬ)"),
        year: Optional[int] = Query(None, description="Year (defaults to current)"),
        current: ResolvedUser = Depends(get_current_user),
    ):
        """Calculate payroll for all employees for a given month."""
        _check_permission(current)
        rows = await _payroll.calculate_payroll(month, year)
        return [PayrollRowOutput(**row.to_dict()) for row in rows]

    @router.get("/calculate/{employee_code}", response_model=PayrollRowOutput | None)
    async def get_employee_payroll(
        employee_code: str,
        month: str = Query(..., description="Month name"),
        year: Optional[int] = Query(None),
        current: ResolvedUser = Depends(get_current_user),
    ):
        """Get detailed payroll for a single employee."""
        _check_permission(current)
        row = await _payroll.get_employee_details(employee_code, month, year)
        if not row:
            return None
        return PayrollRowOutput(**row.to_dict())

    # Sales Plans endpoints
    @router.get("/plans", response_model=list[SalesPlanOutput])
    async def list_plans(current: ResolvedUser = Depends(get_current_user)):
        """List all sales plans."""
        _check_permission(current)
        plans = _plans.list_plans()
        return [
            SalesPlanOutput(
                employee_code=p.employee_code,
                employee_name=p.employee_name,
                repair_plan=p.repair_plan,
                cosmetics_plan=p.cosmetics_plan,
                shoes_plan=p.shoes_plan,
                ignore_kpi=p.ignore_kpi,
            )
            for p in plans
        ]

    @router.get("/plans/{employee_code}", response_model=SalesPlanOutput | None)
    async def get_plan(
        employee_code: str,
        current: ResolvedUser = Depends(get_current_user),
    ):
        """Get sales plan for an employee."""
        _check_permission(current)
        plan = _plans.get_plan(employee_code)
        if not plan:
            return None
        return SalesPlanOutput(
            employee_code=plan.employee_code,
            employee_name=plan.employee_name,
            repair_plan=plan.repair_plan,
            cosmetics_plan=plan.cosmetics_plan,
            shoes_plan=plan.shoes_plan,
            ignore_kpi=plan.ignore_kpi,
        )

    @router.put("/plans", response_model=SalesPlanOutput)
    async def set_plan(
        data: SalesPlanInput,
        current: ResolvedUser = Depends(get_current_user),
    ):
        """Create or update a sales plan."""
        _check_permission(current)
        plan = _plans.set_plan(
            employee_code=data.employee_code,
            employee_name=data.employee_name,
            repair_plan=data.repair_plan,
            cosmetics_plan=data.cosmetics_plan,
            shoes_plan=data.shoes_plan,
            ignore_kpi=data.ignore_kpi,
        )
        return SalesPlanOutput(
            employee_code=plan.employee_code,
            employee_name=plan.employee_name,
            repair_plan=plan.repair_plan,
            cosmetics_plan=plan.cosmetics_plan,
            shoes_plan=plan.shoes_plan,
            ignore_kpi=plan.ignore_kpi,
        )

    @router.delete("/plans/{employee_code}")
    async def delete_plan(
        employee_code: str,
        current: ResolvedUser = Depends(get_current_user),
    ):
        """Delete a sales plan."""
        _check_permission(current)
        deleted = _plans.delete_plan(employee_code)
        if not deleted:
            raise HTTPException(status_code=404, detail="Plan not found")
        return {"status": "deleted"}

    return router
