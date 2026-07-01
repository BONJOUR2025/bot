"""API for courier salary (fixed оклад − авансы ± премии/штрафы) + car mileage.

The courier is on a fixed salary; the page also tracks the car's odometer for the
period (manually or synced from StarLine telematics). Mirrors the manager-salary
flow (advances since last salary, accrue, payout, journal) without KPI.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.payout_service import PayoutService
from app.services.access_control_service import AccessControlService, ResolvedUser
from app.services import starline_client
from app.data.courier_plan_repository import get_courier_plan_repository
from app.data.courier_mileage_repository import get_courier_mileage_repository
from app.data.courier_salary_repository import get_courier_salary_repository

from .dependencies import require_permission
from .manager_salary import _advances_since_last_salary, SALARY_TYPE

COURIER_PERMISSION = "payroll"


def _calc(oklad, advances, bonuses, penalties) -> dict:
    oklad = float(oklad or 0)
    advances = float(advances or 0)
    bonuses = float(bonuses or 0)
    penalties = float(penalties or 0)
    gross = round(oklad + bonuses, 2)
    return {
        "oklad": oklad, "bonuses": bonuses, "penalties": penalties, "advances": advances,
        "gross": gross, "to_pay": round(gross - advances - penalties, 2),
    }


def _prev_period(period: str) -> str:
    y, m = map(int, period.split("-"))
    m -= 1
    if m == 0:
        m, y = 12, y - 1
    return f"{y}-{m:02d}"


def _period_ts(period: str) -> tuple[int, int]:
    """(start, end) epoch seconds for a "YYYY-MM" period."""
    from datetime import datetime
    from calendar import monthrange
    y, m = map(int, period.split("-"))
    last = monthrange(y, m)[1]
    return (int(datetime(y, m, 1).timestamp()),
            int(datetime(y, m, last, 23, 59, 59).timestamp()))


class SalaryInput(BaseModel):
    oklad: float = 0
    advances: float = 0
    bonuses: float = 0
    penalties: float = 0


class PlanInput(BaseModel):
    employee_code: str
    period: str
    oklad: float = 0
    starline_device_id: str = ""


class MileageInput(BaseModel):
    employee_code: str
    period: str
    odometer_start: Optional[float] = None
    odometer_end: Optional[float] = None


class AccrualInput(SalaryInput):
    employee_code: str = ""
    employee_name: str = ""
    user_id: str = ""
    period: str = ""
    date_from: str = ""
    date_to: str = ""
    mileage_km: Optional[float] = None


def create_courier_salary_router(
    payout_service: PayoutService, access_service: AccessControlService
) -> APIRouter:
    router = APIRouter(prefix="/courier-salary", tags=["CourierSalary"])
    perm = require_permission(COURIER_PERMISSION)

    # ── Plan (оклад + привязка StarLine) ──────────────────────────────
    @router.get("/plan")
    async def get_plan(employee_code: str = Query(...), period: str = Query(...),
                       current: ResolvedUser = Depends(perm)):
        return get_courier_plan_repository().get(employee_code, period)

    @router.put("/plan")
    async def put_plan(data: PlanInput, current: ResolvedUser = Depends(perm)):
        return get_courier_plan_repository().upsert(
            data.employee_code, data.period,
            oklad=data.oklad, starline_device_id=data.starline_device_id)

    # ── Advances (как у менеджеров: с последней зарплаты) ──────────────
    @router.get("/advances")
    async def advances(employee_id: str = Query(...), current: ResolvedUser = Depends(perm)):
        return await _advances_since_last_salary(payout_service, employee_id)

    @router.post("/calc")
    async def calc(data: SalaryInput, current: ResolvedUser = Depends(perm)):
        return _calc(data.oklad, data.advances, data.bonuses, data.penalties)

    # ── Mileage ───────────────────────────────────────────────────────
    @router.get("/mileage")
    async def get_mileage(employee_code: str = Query(...), period: str = Query(...),
                          current: ResolvedUser = Depends(perm)):
        return get_courier_mileage_repository().get(employee_code, period)

    @router.put("/mileage")
    async def put_mileage(data: MileageInput, current: ResolvedUser = Depends(perm)):
        # manual entry: clear any track override so km = end − start
        return get_courier_mileage_repository().upsert(
            data.employee_code, data.period,
            odometer_start=data.odometer_start, odometer_end=data.odometer_end,
            km_explicit=None, source="manual", no_signal_km=None, no_signal_gaps=None)

    @router.post("/mileage/sync")
    async def sync_mileage(employee_code: str = Query(...), period: str = Query(...),
                           device_id: Optional[str] = Query(None),
                           current: ResolvedUser = Depends(perm)):
        """Fill the period's mileage from StarLine. If the device exposes an OBD
        odometer, store it as the period's end (carrying the start from the
        previous period). Otherwise (a «Маяк» beacon) use the GPS-track length
        for the period as the distance."""
        plan = get_courier_plan_repository().get(employee_code, period)
        dev = str(device_id or plan.get("starline_device_id") or "")
        if not dev:
            raise HTTPException(status_code=400, detail="Не указано устройство StarLine (device_id)")
        repo = get_courier_mileage_repository()
        odo = await starline_client.get_mileage(dev)
        if odo is not None:
            cur = repo.get(employee_code, period)
            start = cur.get("odometer_start")
            if start is None:
                start = repo.get(employee_code, _prev_period(period)).get("odometer_end")
            return repo.upsert(employee_code, period, odometer_start=start,
                               odometer_end=odo, km_explicit=None, source="starline", no_signal_km=None, no_signal_gaps=None)
        # No odometer (Маяк) → StarLine /ways gives the historical track + mileage
        # for the period; fall back to our accumulated poller track.
        ts_from, ts_to = _period_ts(period)
        diag = await starline_client.get_ways_diagnostics(dev, ts_from, ts_to)
        km, no_signal_km, no_signal_gaps = diag["km"], diag["no_signal_km"], diag["no_signal_gaps"]
        source = "starline-ways"
        if not km:
            from app.data.courier_track_repository import get_courier_track_repository
            km = get_courier_track_repository().mileage(dev, ts_from, ts_to)
            source = "starline-track"
            no_signal_km = no_signal_gaps = None
        if not km:
            if diag.get("rate_limited"):
                retry = diag.get("retry_after")
                suffix = f" Повторите примерно через {retry} сек." if retry else " Повторите попытку через минуту."
                raise HTTPException(status_code=429, detail=f"StarLine временно ограничил частоту запросов.{suffix}")
            raise HTTPException(status_code=502, detail="StarLine не вернул пробег за период (нет трека) — введите пробег вручную")
        return repo.upsert(employee_code, period, km_explicit=km, source=source,
                           no_signal_km=no_signal_km, no_signal_gaps=no_signal_gaps)

    # ── StarLine diagnostics (verify shapes against a real account) ────
    @router.get("/starline/status")
    async def starline_status(current: ResolvedUser = Depends(perm)):
        return await starline_client.get_status()

    @router.get("/starline/devices")
    async def starline_devices(current: ResolvedUser = Depends(perm)):
        try:
            return await starline_client.list_devices()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @router.get("/starline/raw/{device_id}")
    async def starline_raw(device_id: str, current: ResolvedUser = Depends(perm)):
        try:
            return await starline_client.get_device_raw(device_id)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @router.get("/starline/raw-user")
    async def starline_raw_user(current: ResolvedUser = Depends(perm)):
        try:
            return await starline_client.get_user_data()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @router.get("/starline/track/{device_id}")
    async def starline_track(device_id: str, period: str = Query(..., description="YYYY-MM"),
                             current: ResolvedUser = Depends(perm)):
        """Raw GPS track for the period + computed length (km) — for beacons."""
        ts_from, ts_to = _period_ts(period)
        try:
            raw = await starline_client.get_track_raw(device_id, ts_from, ts_to)
            return {"km": await starline_client.get_track_mileage(device_id, ts_from, ts_to), "raw": raw}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @router.get("/starline/probe/{device_id}")
    async def starline_probe(device_id: str, action: str = Query("track"),
                             version: str = Query("2"), period: str = Query("2026-06"),
                             current: ResolvedUser = Depends(perm)):
        """Diagnostic: try an arbitrary device action (track/gps/mileage/run/…) to
        find which one this account exposes. e.g. ?action=track&version=1"""
        ts_from, ts_to = _period_ts(period)
        try:
            return await starline_client.probe(version, device_id, action, ts_from, ts_to)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @router.get("/track/status")
    async def track_status(employee_code: str = Query(...), period: str = Query(...),
                           current: ResolvedUser = Depends(perm)):
        """Accumulated-track status for this courier's device + km for the period."""
        from app.data.courier_track_repository import get_courier_track_repository
        dev = str(get_courier_plan_repository().get(employee_code, period).get("starline_device_id") or "")
        if not dev:
            return {"device_id": None, "points": 0, "km": None}
        ts_from, ts_to = _period_ts(period)
        track = get_courier_track_repository()
        return {"device_id": dev, **track.status(dev), "km": track.mileage(dev, ts_from, ts_to)}

    @router.post("/track/poll")
    async def track_poll(current: ResolvedUser = Depends(perm)):
        """Run one polling pass now (instead of waiting for the 15-min cycle)."""
        from app.services import starline_poller
        return {"stored": await starline_poller.poll_once()}

    @router.get("/starline/ways/{device_id}")
    async def starline_ways(device_id: str,
                            period: str = Query("2026-06", description="YYYY-MM"),
                            date_from: Optional[str] = Query(None, description="YYYY-MM-DD (один день/диапазон)"),
                            date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
                            current: ResolvedUser = Depends(perm)):
        """POST /ways — computed mileage + raw response (diagnostic). Use
        date_from/date_to (YYYY-MM-DD) to limit the range to a day."""
        from datetime import datetime
        if date_from:
            try:
                d2 = date_to or date_from
                ts_from = int(datetime.strptime(date_from, "%Y-%m-%d").timestamp())
                ts_to = int(datetime.strptime(d2, "%Y-%m-%d").replace(hour=23, minute=59, second=59).timestamp())
            except ValueError:
                raise HTTPException(status_code=400, detail="Формат даты: YYYY-MM-DD")
        else:
            ts_from, ts_to = _period_ts(period)
        try:
            raw = await starline_client.get_ways(device_id, ts_from, ts_to)
            no_signal_km, no_signal_gaps = starline_client._ways_no_signal_km(raw)
            return {"km": starline_client._ways_mileage(raw), "no_signal_km": no_signal_km,
                    "no_signal_gaps": no_signal_gaps, "ts_from": ts_from, "ts_to": ts_to, "raw": raw}
        except starline_client.StarLineRateLimited as exc:
            raise HTTPException(status_code=429, detail=f"StarLine rate limit (429). retry_after={exc.retry_after}")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @router.get("/starline/probe-all/{device_id}")
    async def starline_probe_all(device_id: str, period: str = Query("2026-06"),
                                 current: ResolvedUser = Depends(perm)):
        """Diagnostic: try many device actions across versions and report which
        ones return data (to find the mileage/track endpoint this account allows)."""
        ts_from, ts_to = _period_ts(period)
        try:
            return await starline_client.probe_all(device_id, ts_from, ts_to)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    # ── Accrue / journal / payout ─────────────────────────────────────
    @router.post("/accrue")
    async def accrue(data: AccrualInput, current: ResolvedUser = Depends(perm)):
        adv = await _advances_since_last_salary(payout_service, data.employee_code or data.user_id)
        data.advances = adv["total"]
        result = _calc(data.oklad, data.advances, data.bonuses, data.penalties)
        return get_courier_salary_repository().add({
            "employee_code": data.employee_code,
            "employee_name": data.employee_name,
            "user_id": data.user_id,
            "period": data.period,
            "date_from": data.date_from,
            "date_to": data.date_to,
            "mileage_km": data.mileage_km,
            "actor": getattr(current, "login", None) or getattr(current, "id", None),
            "inputs": data.model_dump(),
            "result": result,
            "advances_detail": adv,
            "payout_id": None,
        })

    @router.get("/accruals")
    async def accruals(employee_code: Optional[str] = None, period: Optional[str] = None,
                       limit: int = 200, current: ResolvedUser = Depends(perm)):
        return get_courier_salary_repository().list(
            employee_code=employee_code, period=period, limit=limit)

    @router.delete("/accruals/{accrual_id}")
    async def delete_accrual(accrual_id: int, current: ResolvedUser = Depends(perm)):
        return {"deleted": get_courier_salary_repository().delete(accrual_id)}

    @router.post("/accruals/{accrual_id}/payout")
    async def create_accrual_payout(
        accrual_id: int, method: str = Query("🤝 Наличными"),
        current: ResolvedUser = Depends(perm),
    ):
        from app.schemas.payout import PayoutCreate
        from app.services.users import load_users_map
        repo = get_courier_salary_repository()
        entry = repo.get(accrual_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Начисление не найдено")
        if entry.get("payout_id"):
            raise HTTPException(status_code=409, detail="Выплата уже создана для этого начисления")
        result = entry.get("result") or {}
        amount = round(float(result.get("to_pay") or 0), 2)
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Сумма к выплате ≤ 0 — выплата не создаётся")
        emp_id = str(entry.get("employee_code") or entry.get("user_id") or "")
        emp = load_users_map(archived=None).get(emp_id, {})
        if not access_service.is_employee_visible(current, emp_id):
            raise HTTPException(status_code=403, detail="forbidden")
        payout = await payout_service.create_payout(PayoutCreate(
            user_id=emp_id,
            name=entry.get("employee_name") or emp.get("name") or emp.get("full_name") or "",
            phone=emp.get("phone") or "", card_number=emp.get("card_number") or "",
            bank=emp.get("bank") or "", amount=amount, method=method, payout_type=SALARY_TYPE,
            note=f"Зарплата курьера за {entry.get('period') or ''} "
                 f"(оклад {result.get('oklad', 0)} + премии {result.get('bonuses', 0)} "
                 f"− авансы {result.get('advances', 0)} − штрафы {result.get('penalties', 0)})".strip(),
        ))
        updated = repo.set_fields(accrual_id, payout_id=payout.id)
        return {"payout": payout, "accrual": updated}

    return router
