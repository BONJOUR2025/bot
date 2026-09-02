"""API endpoints for sales analytics dashboard."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .dependencies import require_permission
# Safe to import at module load: fdb_cache resolves the Firebird service
# lazily, so this does not pull the fdb driver import into the API startup
# path. Every handler below reads through it — a hit returns a report the
# warmer already computed, a miss falls through to the same live query
# these endpoints ran before (see app/services/fdb_cache).
from app.services import fdb_cache


def _resolve_range(date_from: Optional[date], date_to: Optional[date]) -> tuple[date, date]:
    """Shared default-range + validation for every /sales/* endpoint below."""
    from app.services.firebird_service import FIREBIRD_AVAILABLE

    if not FIREBIRD_AVAILABLE:
        raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")

    today = date.today()
    df = date_from or (today - timedelta(days=30))
    dt = date_to or today
    if df > dt:
        raise HTTPException(status_code=400, detail="date_from не может быть позже date_to")
    return df, dt


def _parse_csv_list(value: Optional[str]) -> Optional[list[str]]:
    """Comma-separated list -> list, or None if empty/absent. Used for both
    Salon.id lists and category keys."""
    if not value:
        return None
    items = [s.strip() for s in value.split(',') if s.strip()]
    return items or None


_parse_salon_ids = _parse_csv_list


def create_sales_router() -> APIRouter:
    router = APIRouter(
        prefix="/sales",
        tags=["Sales"],
        dependencies=[Depends(require_permission("payroll"))],
    )

    @router.get("/daily")
    async def get_daily_sales(
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
        salon_ids: Optional[str] = Query(default=None, description="Comma-separated Salon.id list"),
    ):
        """Return daily repair + cosmetics sales by employee for a date range."""
        from app.services.firebird_service import run_with_timeout

        df, dt = _resolve_range(date_from, date_to)
        try:
            return await run_with_timeout(
                fdb_cache.get_or_compute, "sales.daily", (df, dt, _parse_salon_ids(salon_ids)),
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Сузьте период и попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/client-retention")
    async def get_client_retention(
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
        salon_ids: Optional[str] = Query(default=None, description="Comma-separated Salon.id list"),
    ):
        """Return new-vs-returning client counts for a date range."""
        from app.services.firebird_service import run_with_timeout

        df, dt = _resolve_range(date_from, date_to)
        try:
            return await run_with_timeout(
                fdb_cache.get_or_compute, "sales.client_retention", (df, dt, _parse_salon_ids(salon_ids)),
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Сузьте период и попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/margin")
    async def get_margin_summary(
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
        salon_ids: Optional[str] = Query(default=None, description="Comma-separated Salon.id list"),
    ):
        """Return gross-margin breakdown (repair/cosmetics, by employee) for a date range."""
        from app.services.firebird_service import run_with_timeout

        df, dt = _resolve_range(date_from, date_to)
        try:
            return await run_with_timeout(
                fdb_cache.get_or_compute, "sales.margin", (df, dt, _parse_salon_ids(salon_ids)),
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Сузьте период и попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/turnaround")
    async def get_turnaround_stats(
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
        salon_ids: Optional[str] = Query(default=None, description="Comma-separated Salon.id list"),
        service_search: Optional[str] = Query(default=None, description="Substring match on service/goods name"),
        categories: Optional[str] = Query(default=None, description="Comma-separated category keys"),
    ):
        """Return order fulfillment time (accepted → "Исполненный") and lateness rate by salon."""
        from app.services.firebird_service import run_with_timeout

        df, dt = _resolve_range(date_from, date_to)
        try:
            return await run_with_timeout(
                fdb_cache.get_or_compute, "sales.turnaround",
                (df, dt, _parse_salon_ids(salon_ids), service_search, _parse_csv_list(categories)),
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Сузьте период и попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/receivables")
    async def get_receivables(
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
    ):
        """Return unpaid/partially-paid orders created in a date range."""
        from app.services.firebird_service import run_with_timeout

        df, dt = _resolve_range(date_from, date_to)
        try:
            return await run_with_timeout(fdb_cache.get_or_compute, "sales.receivables", (df, dt))
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Сузьте период и попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/orders")
    async def get_orders_for_period(
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
        salon_ids: Optional[str] = Query(default=None, description="Comma-separated Salon.id list"),
        search: Optional[str] = Query(default=None, description="Поиск по номеру заказа или клиенту"),
        limit: int = Query(default=500, ge=1, le=2000),
        employee_codes: Optional[str] = Query(default=None, description="Comma-separated employee codes"),
        categories: Optional[str] = Query(default=None, description="Comma-separated category keys"),
    ):
        """Список заказов за период для вкладки «Заказы».

        Намеренно без fdb_cache: у этой выдачи есть свободный текстовый
        поиск и лимит, то есть ключ кэша получался бы почти уникальным на
        каждый запрос — кэш только раздувал бы hr.db, ничего не ускоряя.
        """
        from app.services.firebird_service import get_firebird_service, run_with_timeout

        df, dt = _resolve_range(date_from, date_to)
        try:
            svc = get_firebird_service()
            return await run_with_timeout(
                svc.get_orders_for_period, df, dt, _parse_salon_ids(salon_ids), search, limit,
                _parse_csv_list(employee_codes), _parse_csv_list(categories),
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Сузьте период и попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/unclaimed")
    async def get_unclaimed_orders(
        days: int = Query(default=90, ge=1, le=1095),
    ):
        """Return orders past their promised pickup date with no actual pickup yet."""
        from app.services.firebird_service import run_with_timeout, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")

        try:
            return await run_with_timeout(fdb_cache.get_or_compute, "sales.unclaimed", (days,))
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Сузьте период и попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/returns")
    async def get_returns_summary(
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
        salon_ids: Optional[str] = Query(default=None, description="Comma-separated Salon.id list"),
        categories: Optional[str] = Query(default=None, description="Comma-separated category keys"),
    ):
        """Return returned-order counts/amounts by employee for a date range."""
        from app.services.firebird_service import run_with_timeout

        df, dt = _resolve_range(date_from, date_to)
        try:
            return await run_with_timeout(
                fdb_cache.get_or_compute, "sales.returns",
                (df, dt, _parse_salon_ids(salon_ids), _parse_csv_list(categories)),
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Сузьте период и попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/workplaces")
    async def get_workplace_summary(
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
        salon_ids: Optional[str] = Query(default=None, description="Comma-separated Salon.id list"),
    ):
        """Return revenue/volume throughput per work place (repair intake/dispatch checkpoints) for a date range."""
        from app.services.firebird_service import run_with_timeout

        df, dt = _resolve_range(date_from, date_to)
        try:
            return await run_with_timeout(
                fdb_cache.get_or_compute, "sales.workplaces", (df, dt, _parse_salon_ids(salon_ids)),
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Сузьте период и попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/departments")
    async def get_department_comparison(
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
        salon_ids: Optional[str] = Query(default=None, description="Comma-separated Salon.id list"),
        categories: Optional[str] = Query(default=None, description="Comma-separated category keys"),
        employee_codes: Optional[str] = Query(default=None, description="Comma-separated employee codes"),
    ):
        """Return revenue/order comparison by salon for a date range."""
        from app.services.firebird_service import run_with_timeout

        df, dt = _resolve_range(date_from, date_to)
        try:
            return await run_with_timeout(
                fdb_cache.get_or_compute, "sales.departments",
                (df, dt, _parse_salon_ids(salon_ids),
                 _parse_csv_list(categories), _parse_csv_list(employee_codes)),
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Сузьте период и попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/top-products")
    async def get_top_products(
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        salon_ids: Optional[str] = Query(default=None, description="Comma-separated Salon.id list"),
        categories: Optional[str] = Query(default=None, description="Comma-separated subset of repair,cosmetics"),
        employee_codes: Optional[str] = Query(default=None, description="Comma-separated employee codes"),
    ):
        """Return top/bottom-selling SKUs and biggest risers/fallers vs the preceding period."""
        from app.services.firebird_service import run_with_timeout

        df, dt = _resolve_range(date_from, date_to)
        try:
            return await run_with_timeout(
                fdb_cache.get_or_compute, "sales.top_products",
                (df, dt, limit, _parse_salon_ids(salon_ids),
                 _parse_csv_list(categories), _parse_csv_list(employee_codes)),
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Сузьте период и попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/salon-options")
    async def get_salon_options():
        """Return {id, name} for every salon — feeds the "Салон" filter's
        options. A dedicated endpoint under /sales rather than reusing
        GET /api/salons/, which requires the separate "salons" permission:
        that would silently break the filter for anyone with "payroll" but
        not "salons" access, since everything else on this page is gated
        on "payroll" alone.
        """
        from app.data.salon_repository import get_salon_repository

        repo = get_salon_repository()
        return [{"id": s.id, "name": s.name} for s in repo.list_salons()]

    @router.get("/plans")
    async def get_plans(month_keys: Optional[str] = Query(default=None)):
        """Return sales plans keyed by month_key → employee_code → {repair_plan, cosmetics_plan, shoes_plan}.

        month_keys: comma-separated list of month keys like ЯНВАРЬ_2025,ФЕВРАЛЬ_2025
        """
        from app.data.sales_plans_repository import get_sales_plans_repository

        repo = get_sales_plans_repository()
        if not month_keys:
            return {}

        keys = [k.strip() for k in month_keys.split(',') if k.strip()]
        result: dict = {}
        for key in keys:
            plans_map = repo.get_plans_map(month_key=key)
            result[key] = {
                code: {
                    "repair_plan":    p.repair_plan,
                    "cosmetics_plan": p.cosmetics_plan,
                    "shoes_plan":     p.shoes_plan,
                }
                for code, p in plans_map.items()
            }
        return result

    return router
