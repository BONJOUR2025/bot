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


# ── кабинет менеджера ──────────────────────────────────────────────────
# Менеджер видит свой KPI за месяц: тот же расчёт, что на странице
# «Менеджеры» у бухгалтера (план из manager_plan_repository, факт из amoCRM,
# авансы с последней зарплаты, премии и штрафы), но только по себе — id
# берётся из сессии, а не из запроса, поэтому права не нужны. Без блока
# «Контроль» (подозрительные переносы сделок): это инструмент проверки
# менеджера, а не его рабочий экран.

_SELF_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_SELF_TTL = 600  # amoCRM отвечает десятки секунд — не дёргаем его на каждое открытие


def _month_range(period: str):
    from calendar import monthrange
    from datetime import date, datetime

    try:
        y, m = (int(x) for x in period.split("-"))
        start = date(y, m, 1)
    except Exception:
        raise HTTPException(status_code=400, detail="Период в формате YYYY-MM")
    end = date(y, m, monthrange(y, m)[1])
    today = date.today()
    if start > today:
        raise HTTPException(status_code=400, detail="Этот месяц ещё не начался")
    end = min(end, today)
    return start, end, datetime.combine(start, datetime.min.time()), datetime.combine(end, datetime.max.time())


def create_manager_self_router(payout_service: PayoutService) -> APIRouter:
    router = APIRouter(prefix="/managers/me", tags=["ManagerSalary"])

    @router.get("/kpi")
    async def my_kpi(
        period: Optional[str] = Query(None, description="YYYY-MM, по умолчанию текущий"),
        refresh: bool = Query(False),
        current: ResolvedUser = Depends(get_current_user),
    ):
        import time
        from datetime import date

        from app.data.employee_repository import EmployeeRepository
        from app.data.incentive_repository import IncentiveRepository
        from app.data.manager_plan_repository import get_manager_plan_repository
        from app.services.amo_metrics import compute_metrics
        from app.services.manager_salary import is_manager_position

        emp_id = current.employee_id
        employee = EmployeeRepository().get_employee(emp_id) if emp_id else None
        if employee is None or not is_manager_position(employee.position):
            raise HTTPException(status_code=403, detail="Раздел для менеджеров по работе с клиентами.")
        period = period or date.today().strftime("%Y-%m")
        d_from, d_to, dt_from, dt_to = _month_range(period)

        key = (str(emp_id), period)
        hit = _SELF_CACHE.get(key)
        if hit and not refresh and time.time() - hit[0] < _SELF_TTL:
            return hit[1]

        plan = get_manager_plan_repository().get(str(emp_id), period)
        amo_id = str(getattr(employee, "amo_user_id", "") or "").strip()
        metrics, metrics_error = None, None
        if not amo_id:
            metrics_error = "Ваш профиль не связан с amoCRM — обратитесь к руководителю."
        else:
            try:
                metrics = await compute_metrics(dt_from, dt_to, int(amo_id), detail=True)
            except Exception:
                metrics_error = "amoCRM сейчас не отвечает, попробуйте позже."
        advances = await _advances_since_last_salary(payout_service, str(emp_id))
        inc = IncentiveRepository().list(str(emp_id), None, d_from.isoformat(), d_to.isoformat())
        bonuses = sum(float(i.get("amount") or 0) for i in inc if i.get("type") == "bonus")
        penalties = sum(float(i.get("amount") or 0) for i in inc if i.get("type") == "penalty")
        m = metrics or {}
        result = _calc(SalaryInput(
            oklad=plan.get("oklad") or 0, kpi_max=plan.get("kpi_max") or 0,
            revenue_plan=plan.get("revenue_plan") or 0, revenue_actual=m.get("revenue_actual") or 0,
            repair_plan_conv=plan.get("repair_plan_conv") or 0,
            repair_target_deals=m.get("repair_target_deals") or 0, repair_total_deals=m.get("repair_total_deals") or 0,
            sew_plan_conv=plan.get("sew_plan_conv") or 0,
            sew_target_deals=m.get("sew_target_deals") or 0, sew_total_deals=m.get("sew_total_deals") or 0,
            sew_new_leads=m.get("sew_new_leads") or 0,
            advances=advances["total"], bonuses=bonuses, penalties=penalties,
        ))
        items = (m.get("items") or {})
        accruals = get_manager_salary_repository().list(employee_code=str(emp_id), limit=12)
        payload = {
            "period": period,
            "date_from": d_from.isoformat(),
            "date_to": d_to.isoformat(),
            "name": employee.full_name or employee.name,
            "plan_set": bool(plan.get("oklad") or plan.get("kpi_max") or plan.get("revenue_plan")),
            "result": result,
            "metrics_error": metrics_error,
            "response": {
                "avg_seconds": m.get("avg_response_seconds"),
                "median_seconds": m.get("median_response_seconds"),
                "sample": m.get("response_sample"),
                "slowest": (items.get("response") or [])[:10],
            },
            "deals": {
                "won": items.get("revenue") or [],
                "repair_total": len(items.get("repair_denom") or []),
                "sew_total": len(items.get("sew_denom") or []),
            },
            "incentives": [{"date": i.get("date"), "type": i.get("type"), "amount": i.get("amount"),
                            "reason": i.get("reason") or i.get("comment") or ""} for i in inc],
            "advances": advances,
            "accruals": [{"id": a.get("id"), "period": a.get("period"),
                          "to_pay": (a.get("result") or {}).get("to_pay"),
                          "gross": (a.get("result") or {}).get("gross"),
                          "paid": bool(a.get("payout_id")), "created_at": a.get("created_at")} for a in accruals],
            "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        }
        if metrics is not None:
            _SELF_CACHE[key] = (time.time(), payload)
        return payload

    return router
