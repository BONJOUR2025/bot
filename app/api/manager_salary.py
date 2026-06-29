"""API for manager salary (оклад + KPI), accruals and advance deduction."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.payout_service import PayoutService
from app.services.access_control_service import AccessControlService, ResolvedUser
from app.services.manager_salary import calc_manager_salary
from app.data.manager_salary_repository import get_manager_salary_repository
from app.schemas.payout import PayoutCreate

from .dependencies import get_current_user, require_permission

MANAGER_SALARY_PERMISSION = "manager-salary"
ADVANCE_TYPE = "Аванс"
SALARY_TYPE = "Зарплата"
VALID_PAYOUT_STATUSES = {"Одобрено", "Выплачено"}


async def _advances_since_last_salary(payout_service: PayoutService, employee_id: str) -> dict:
    """Advances issued SINCE the last salary payout: sum of «Аванс» payouts
    (Одобрено/Выплачено) after the manager's last «Зарплата» payout; if there is
    none — all such advances. Single source of truth for both the GET endpoint
    and the server-side recompute at accrual time."""
    rows = await payout_service.list_payouts(employee_id=employee_id)

    def _ts(p):
        return str(p.timestamp) if p.timestamp else ""

    rows = sorted(rows, key=_ts)
    last_salary_ts = ""
    for p in rows:
        if p.payout_type == SALARY_TYPE and p.status in VALID_PAYOUT_STATUSES:
            last_salary_ts = _ts(p)

    adv = [p for p in rows
           if p.payout_type == ADVANCE_TYPE and p.status in VALID_PAYOUT_STATUSES
           and (not last_salary_ts or _ts(p) > last_salary_ts)]
    total = round(sum(float(p.amount or 0) for p in adv), 2)
    return {"total": total, "count": len(adv), "since": last_salary_ts or None,
            "items": [{"id": p.id, "amount": p.amount, "status": p.status,
                       "timestamp": _ts(p)} for p in adv]}


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
    bonuses: float = 0
    penalties: float = 0


class PlanInput(BaseModel):
    employee_code: str
    period: str
    oklad: float = 0
    kpi_max: float = 0
    revenue_plan: float = 0
    repair_plan_conv: float = 0.50
    sew_plan_conv: float = 0.25


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
        advances=data.advances, bonuses=data.bonuses, penalties=data.penalties,
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

    @router.get("/metrics")
    async def metrics(
        date_from: str = Query(..., description="YYYY-MM-DD"),
        date_to: str = Query(..., description="YYYY-MM-DD"),
        amo_user_id: Optional[int] = Query(None),
        detail: bool = Query(False, description="include per-deal drill-down"),
        current: ResolvedUser = Depends(require_permission(MANAGER_SALARY_PERMISSION)),
    ):
        """Pull the fact metrics (revenue, deal counts, leads) from amoCRM for
        the period. With detail=1 also returns the concrete deals counted in each
        group. 502 if amoCRM is unavailable."""
        from datetime import datetime
        from app.services.amo_metrics import compute_metrics
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            raise HTTPException(status_code=400, detail="Формат даты: YYYY-MM-DD")
        try:
            return await compute_metrics(dt_from, dt_to, amo_user_id, detail=detail)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @router.get("/advances")
    async def advances(
        employee_id: str = Query(...),
        current: ResolvedUser = Depends(require_permission(MANAGER_SALARY_PERMISSION)),
    ):
        """Advances issued SINCE the last salary payout (как в расчёте ЗП)."""
        return await _advances_since_last_salary(payout_service, employee_id)

    @router.get("/plan")
    async def get_plan(
        employee_code: str = Query(...),
        period: str = Query(...),
        current: ResolvedUser = Depends(require_permission(MANAGER_SALARY_PERMISSION)),
    ):
        from app.data.manager_plan_repository import get_manager_plan_repository
        return get_manager_plan_repository().get(employee_code, period)

    @router.get("/plans")
    async def list_plans(
        period: str = Query(...),
        current: ResolvedUser = Depends(require_permission(MANAGER_SALARY_PERMISSION)),
    ):
        from app.data.manager_plan_repository import get_manager_plan_repository
        return get_manager_plan_repository().list(period)

    @router.put("/plan")
    async def put_plan(
        data: PlanInput,
        current: ResolvedUser = Depends(require_permission(MANAGER_SALARY_PERMISSION)),
    ):
        from app.data.manager_plan_repository import get_manager_plan_repository
        return get_manager_plan_repository().upsert(
            data.employee_code, data.period,
            oklad=data.oklad, kpi_max=data.kpi_max,
            revenue_plan=data.revenue_plan,
            repair_plan_conv=data.repair_plan_conv,
            sew_plan_conv=data.sew_plan_conv,
        )

    @router.post("/accrue")
    async def accrue(
        data: AccrualInput,
        current: ResolvedUser = Depends(require_permission(MANAGER_SALARY_PERMISSION)),
    ):
        """Recompute server-side and store the accrual with its full breakdown.

        Advances are re-verified here against the «Выплаты» journal (авансы с
        последней зарплаты) so the stored списание is authoritative — the client
        value is ignored. The accrual records both начисления (оклад, KPI,
        премии) and списания (авансы, штрафы)."""
        adv = await _advances_since_last_salary(
            payout_service, data.employee_code or data.user_id)
        data.advances = adv["total"]   # authoritative server-side value
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
            "advances_detail": adv,   # какие авансы списаны и с какого момента
            "payout_id": None,        # ссылка на созданную выплату (если будет)
        })
        return entry

    @router.post("/accruals/{accrual_id}/payout")
    async def create_accrual_payout(
        accrual_id: int,
        method: str = Query("🤝 Наличными", description="способ выплаты"),
        current: ResolvedUser = Depends(require_permission(MANAGER_SALARY_PERMISSION)),
    ):
        """Create a «Зарплата» payout for an accrual with the «К выплате» amount
        auto-filled (оклад + комиссия + премия − штраф − аванс). Idempotent: a
        second call returns the already-linked payout id without creating a
        duplicate."""
        repo = get_manager_salary_repository()
        entry = repo.get(accrual_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Начисление не найдено")
        if entry.get("payout_id"):
            raise HTTPException(status_code=409, detail="Выплата уже создана для этого начисления")

        result = entry.get("result") or {}
        amount = round(float(result.get("to_pay") or 0), 2)
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Сумма к выплате ≤ 0 — выплата не создаётся")

        from app.services.users import load_users_map
        emp_id = str(entry.get("employee_code") or entry.get("user_id") or "")
        emp = load_users_map(archived=None).get(emp_id, {})
        if not access_service.is_employee_visible(current, emp_id):
            raise HTTPException(status_code=403, detail="forbidden")

        payout = await payout_service.create_payout(PayoutCreate(
            user_id=emp_id,
            name=entry.get("employee_name") or emp.get("name") or emp.get("full_name") or "",
            phone=emp.get("phone") or "",
            card_number=emp.get("card_number") or "",
            bank=emp.get("bank") or "",
            amount=amount,
            method=method,
            payout_type=SALARY_TYPE,
            note=f"Зарплата менеджера за {entry.get('period') or ''} "
                 f"(оклад {result.get('oklad', 0)} + KPI {result.get('kpi', 0)} "
                 f"+ премии {result.get('bonuses', 0)} − авансы {result.get('advances', 0)} "
                 f"− штрафы {result.get('penalties', 0)})".strip(),
        ))
        updated = repo.set_fields(accrual_id, payout_id=payout.id)
        return {"payout": payout, "accrual": updated}

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
