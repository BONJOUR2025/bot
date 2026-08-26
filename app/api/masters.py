"""API endpoints for master works dashboard."""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .dependencies import get_current_user, require_permission
from app.services.access_control_service import ResolvedUser
from app.services.masters_service import resolve_works_range


class AttendanceMarkInput(BaseModel):
    date: date
    note: str = ""


def create_masters_router() -> APIRouter:
    router = APIRouter(
        prefix="/masters",
        tags=["Masters"],
        dependencies=[Depends(require_permission("payroll"))],
    )

    @router.get("/works")
    async def get_works(
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
    ):
        """Return aggregated service works with warnings and salary summary."""
        from app.services.firebird_service import run_with_timeout
        from app.services import fdb_cache
        from app.services.masters_service import FIREBIRD_AVAILABLE, fetch_works_stale

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Firebird недоступен: драйвер fdb не установлен.",
            )

        df, dt, clamped = resolve_works_range(date_from, date_to)
        extra = {"range_clamped": True, "date_from": df.isoformat(), "date_to": dt.isoformat()} if clamped else {}

        try:
            # A cache hit returns in milliseconds; a miss falls through to
            # the same live fetch_works this always ran. run_with_timeout
            # bounds that at 55s and, on timeout, kills the query's own
            # Firebird attachment so it can't leak past the deadline (see
            # firebird_service.run_with_timeout for why a bare
            # asyncio.wait_for isn't enough here).
            result = await run_with_timeout(
                fdb_cache.get_or_compute, "masters.works", (df, dt), timeout=55,
            )
        except asyncio.TimeoutError:
            # Measured on this DB, the same month costs ~17s when the Agbis
            # server is quiet and runs past the 55s budget when it is not, so
            # a timeout here says "Firebird is busy right now", not "this
            # range is unanswerable". Returning the last good report for the
            # same range keeps the page usable and, more importantly, stops
            # the retry loop that was adding a fresh 55s query per click to a
            # server already saturated (five straight 504s on 2026-07-28
            # 18:01-18:05 came in exactly that shape).
            #
            # Two places can hold that last good report: the shared on-disk
            # cache (written by the warmer, possibly past its TTL — which is
            # exactly what "stale" means and is preferred here), and this
            # process's own in-memory cache from an earlier live compute.
            expired = fdb_cache.peek("masters.works", (df, dt))
            if expired is None:
                expired = fetch_works_stale(df, dt)
            if expired is not None:
                cached, age = expired
                return {**cached, "stale": True, "stale_age_sec": int(age), **extra}
            raise HTTPException(
                status_code=504,
                detail="Запрос выполняется слишком долго. Выберите период покороче (например, один месяц) и попробуйте снова.",
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        return {**result, **extra} if extra else result

    @router.get("/apprentices")
    async def get_apprentices(
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
    ):
        """Stipend report for «Ученик мастера» employees: 2000₽ per calendar
        day of turnstile attendance in the period, minus advances since
        their last salary payout. See masters_service.get_apprentice_stipends
        for the attendance/matching rules.
        """
        from app.services.firebird_service import run_with_timeout
        from app.services.masters_service import FIREBIRD_AVAILABLE, get_apprentice_stipends

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Firebird недоступен: драйвер fdb не установлен.",
            )

        df, dt, clamped = resolve_works_range(date_from, date_to)
        extra = {"range_clamped": True, "date_from": df.isoformat(), "date_to": dt.isoformat()} if clamped else {}

        try:
            rows = await run_with_timeout(get_apprentice_stipends, df, dt, timeout=30)
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Запрос выполняется слишком долго. Выберите период покороче и попробуйте снова.",
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        return {"apprentices": rows, **extra}

    @router.post("/apprentices/{employee_id}/attendance")
    async def add_apprentice_mark(
        employee_id: str,
        data: AttendanceMarkInput,
        current: ResolvedUser = Depends(get_current_user),
    ):
        """Manually mark a training day for an apprentice — turnstile
        presence is the primary source (see get_apprentice_stipends) but
        misses a forgotten badge, a broken turnstile, or a day spent
        off-site. Idempotent per (employee_id, date): adding again just
        updates the note.
        """
        from app.data.employee_repository import EmployeeRepository
        from app.data.apprentice_attendance_repository import get_apprentice_attendance_repository
        from app.services.masters_service import APPRENTICE_POSITION

        emp = EmployeeRepository().get_employee(employee_id)
        if emp is None:
            raise HTTPException(status_code=404, detail="Сотрудник не найден")
        if emp.position != APPRENTICE_POSITION:
            raise HTTPException(status_code=400, detail=f'У сотрудника не должность «{APPRENTICE_POSITION}»')

        author = getattr(current, "login", None) or getattr(current, "id", "admin")
        rec = get_apprentice_attendance_repository().add_mark(
            employee_id, data.date, note=data.note.strip(), author=str(author),
        )
        return rec

    @router.delete("/apprentices/{employee_id}/attendance/{mark_date}")
    async def remove_apprentice_mark(employee_id: str, mark_date: date):
        from app.data.apprentice_attendance_repository import get_apprentice_attendance_repository

        removed = get_apprentice_attendance_repository().remove_mark(employee_id, mark_date)
        if not removed:
            raise HTTPException(status_code=404, detail="Отметка не найдена")
        return {"status": "deleted"}

    return router
