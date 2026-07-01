"""API for courier salary (fixed оклад − авансы ± премии/штрафы) + car mileage.

The courier is on a fixed salary; the page also tracks the car's odometer for the
period (manually or synced from StarLine telematics). Mirrors the manager-salary
flow (advances since last salary, accrue, payout, journal) without KPI.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.payout_service import PayoutService
from app.services.access_control_service import AccessControlService, ResolvedUser
from app.services import starline_client, yandex_router_client
from app.data.courier_plan_repository import get_courier_plan_repository
from app.data.courier_mileage_repository import get_courier_mileage_repository
from app.data.courier_salary_repository import get_courier_salary_repository

from .dependencies import require_permission
from .manager_salary import _advances_since_last_salary, SALARY_TYPE

COURIER_PERMISSION = "payroll"

# Safety net independent of routing_min_km: however low the threshold, never
# fire more than this many Router API calls for one diagnostics request —
# Yandex Router API is a paid product past its trial quota, and a fat-fingered
# routing_min_km=0 over a 2000-gap month shouldn't be able to burn the quota
# in one request.
MAX_ROUTED_GAPS = 200
ROUTING_CONCURRENCY = 4


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


async def refine_gaps_with_routing(
    gaps: list[dict], min_km: float,
    route_fn=yandex_router_client.route_distance_km,
    max_gaps: int = MAX_ROUTED_GAPS, concurrency: int = ROUTING_CONCURRENCY,
) -> dict:
    """Re-measure NO_SIGNAL gaps (>= min_km, capped at max_gaps) via a routing
    function (Yandex Router API by default; injectable for tests) instead of
    trusting the straight-line estimate. Each gap that gets a road distance
    carries it as "road_km"; gaps below the threshold, over the cap, or where
    routing failed keep only "km" (straight-line) and are summed as-is.
    Mutates the "gaps" entries in place (adds "road_km" where resolved)."""
    candidates = [g for g in gaps if not g.get("excluded") and g["km"] >= min_km]
    capped = candidates[:max_gaps]
    skipped_over_cap = max(len(candidates) - len(capped), 0)

    sem = asyncio.Semaphore(concurrency)

    async def route_one(g: dict) -> None:
        async with sem:
            road_km = await route_fn(g["start"]["y"], g["start"]["x"], g["finish"]["y"], g["finish"]["x"])
        if road_km is not None:
            g["road_km"] = road_km

    await asyncio.gather(*[route_one(g) for g in capped])

    total_km = sum(g.get("road_km", g["km"]) for g in gaps if not g.get("excluded"))
    routed_count = sum(1 for g in capped if "road_km" in g)
    return {
        "km": round(total_km, 1),
        "routed_count": routed_count,
        "routed_requested": len(capped),
        "skipped_over_cap": skipped_over_cap,
        "top_gaps": sorted(
            (g for g in gaps if not g.get("excluded")),
            key=lambda g: g.get("road_km", g["km"]), reverse=True,
        )[:15],
    }


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

    @router.get("/yandex/status")
    async def yandex_router_status(current: ResolvedUser = Depends(perm)):
        return {"configured": yandex_router_client.is_configured()}

    @router.get("/yandex/route-raw")
    async def yandex_route_raw(lat1: float = Query(...), lon1: float = Query(...),
                               lat2: float = Query(...), lon2: float = Query(...),
                               current: ResolvedUser = Depends(perm)):
        """Diagnostic: raw Yandex Router API response for one pair of points —
        use this once a real YANDEX_ROUTER_API_KEY is set to verify the
        distance field is where yandex_router_client._find_distance_m expects
        it (documented shape, not yet exercised against a live key in this
        project); adjust that function if the real payload differs."""
        try:
            raw = await yandex_router_client.get_route_raw(lat1, lon1, lat2, lon2)
            parsed_m = yandex_router_client._find_distance_m(raw)
            return {"parsed_km": None if parsed_m is None else round(parsed_m / 1000, 2), "raw": raw}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

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
            signal = starline_client._ways_no_signal_km(raw)
            return {"km": starline_client._ways_mileage(raw), "no_signal_km": signal["km"],
                    "no_signal_gaps": signal["gaps"], "no_signal_excluded_count": signal["excluded_count"],
                    "no_signal_excluded_km": signal["excluded_km"], "no_signal_top_gaps": signal["top_gaps"],
                    "ts_from": ts_from, "ts_to": ts_to, "raw": raw}
        except starline_client.StarLineRateLimited as exc:
            raise HTTPException(status_code=429, detail=f"StarLine rate limit (429). retry_after={exc.retry_after}")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    async def _mileage_diagnostics(dev: str, date_from: str, date_to: str,
                                    odometer_start: Optional[float], odometer_end: Optional[float],
                                    use_routing: bool, routing_min_km: float,
                                    extra: dict) -> dict:
        """Shared by the employee_code and device_id diagnostic routes."""
        from datetime import datetime
        try:
            ts_from = int(datetime.strptime(date_from, "%Y-%m-%d").timestamp())
            ts_to = int(datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59).timestamp())
        except ValueError:
            raise HTTPException(status_code=400, detail="Формат даты: YYYY-MM-DD")

        diag = await starline_client.get_ways_diagnostics(dev, ts_from, ts_to)
        km = diag["km"]
        no_signal_km = diag["no_signal_km"]
        no_signal_top_gaps = diag["no_signal_top_gaps"]
        routing_info = None

        if use_routing:
            if not yandex_router_client.is_configured():
                raise HTTPException(status_code=400, detail="YANDEX_ROUTER_API_KEY не настроен в .env — уточнение по дорогам недоступно")
            refined = await refine_gaps_with_routing(diag["no_signal_all_gaps"], routing_min_km)
            no_signal_km = refined["km"]
            no_signal_top_gaps = refined["top_gaps"]
            routing_info = {
                "routed_count": refined["routed_count"],
                "routing_min_km": routing_min_km,
                "skipped_over_cap": refined["skipped_over_cap"],
            }

        result = {
            **extra,
            "device_id": dev,
            "date_from": date_from,
            "date_to": date_to,
            "gps_km": km,
            "no_signal_km": no_signal_km,
            "no_signal_gaps": diag["no_signal_gaps"],
            "no_signal_excluded_count": diag["no_signal_excluded_count"],
            "no_signal_excluded_km": diag["no_signal_excluded_km"],
            "no_signal_top_gaps": no_signal_top_gaps,
            "routing": routing_info,
            "estimated_range_km": None if km is None else [km, round(km + no_signal_km, 1)],
            "rate_limited": diag.get("rate_limited", False),
            "retry_after": diag.get("retry_after"),
            "note": (
                "estimated_range_km — нижняя граница (по треку) и оценка сверху (+ разрывы GPS, "
                + ("по дорогам через Yandex Router API" if use_routing else "по прямой")
                + ", без явно битых точек). Реальный одометр обычно попадает в этот диапазон или чуть выше. "
                "no_signal_excluded_km — сумма разрывов длиннее "
                f"{starline_client.NO_SIGNAL_GAP_SANITY_KM} км за один скачок: это почти всегда битые координаты "
                "устройства (например «нулевой остров» 0°,0°), а не реальная езда — не входят в km/no_signal_km. "
                + ("" if use_routing else "Добавьте &use_routing=true, чтобы уточнить разрывы по дорогам "
                   "вместо прямой линии (нужен YANDEX_ROUTER_API_KEY в .env; ограничено "
                   f"{MAX_ROUTED_GAPS} запросами и порогом routing_min_km, по умолчанию 1 км).")
            ),
        }
        if odometer_start is not None and odometer_end is not None:
            real_km = round(odometer_end - odometer_start, 1)
            result["odometer_km"] = real_km
            result["odometer_vs_gps_diff_km"] = None if km is None else round(real_km - km, 1)
            result["odometer_vs_gps_diff_pct"] = None if not km else round((real_km - km) / km * 100, 1)
        return result

    @router.get("/diagnostics/device/{device_id}")
    async def mileage_diagnostics_by_device(device_id: str,
                                            date_from: str = Query(..., description="YYYY-MM-DD"),
                                            date_to: str = Query(..., description="YYYY-MM-DD"),
                                            odometer_start: Optional[float] = Query(None, description="Реальные показания одометра на начало периода — для сверки"),
                                            odometer_end: Optional[float] = Query(None, description="Реальные показания одометра на конец периода — для сверки"),
                                            use_routing: bool = Query(False, description="Уточнить разрывы GPS по дорогам через Yandex Router API вместо прямой линии"),
                                            routing_min_km: float = Query(1.0, description="Считать маршрут только для разрывов от этого числа км (экономия запросов)"),
                                            current: ResolvedUser = Depends(perm)):
        """Browser-friendly diagnostic straight by StarLine device_id — no
        employee_code/plan lookup involved. Paste the URL (with a valid
        session cookie) to see raw GPS-derived mileage for an arbitrary date
        range. Pass odometer_start/odometer_end to see the delta against a
        real odometer reading in the same response."""
        return await _mileage_diagnostics(device_id, date_from, date_to, odometer_start, odometer_end, use_routing, routing_min_km, {})

    @router.get("/diagnostics/{employee_code}")
    async def mileage_diagnostics(employee_code: str,
                                  date_from: str = Query(..., description="YYYY-MM-DD"),
                                  date_to: str = Query(..., description="YYYY-MM-DD"),
                                  odometer_start: Optional[float] = Query(None, description="Реальные показания одометра на начало периода — для сверки"),
                                  odometer_end: Optional[float] = Query(None, description="Реальные показания одометра на конец периода — для сверки"),
                                  use_routing: bool = Query(False, description="Уточнить разрывы GPS по дорогам через Yandex Router API вместо прямой линии"),
                                  routing_min_km: float = Query(1.0, description="Считать маршрут только для разрывов от этого числа км (экономия запросов)"),
                                  device_id: Optional[str] = Query(None),
                                  current: ResolvedUser = Depends(perm)):
        """Same as /diagnostics/device/{device_id}, but resolves the device
        from the courier's plan (either month touched by the range) so you
        don't have to look device_id up by hand."""
        dev = str(device_id or "")
        if not dev:
            plan_repo = get_courier_plan_repository()
            for period in {date_to[:7], date_from[:7]}:
                dev = str(plan_repo.get(employee_code, period).get("starline_device_id") or "")
                if dev:
                    break
        if not dev:
            raise HTTPException(status_code=400, detail="У сотрудника не привязано устройство StarLine ни на один из месяцев периода — передайте device_id вручную")
        return await _mileage_diagnostics(dev, date_from, date_to, odometer_start, odometer_end, use_routing, routing_min_km, {"employee_code": employee_code})

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
