"""Кабинет мастера — в вебе и в приложении «BONJOUR Мастер».

Те же данные, что раздел мастера в Telegram-боте (master_bot_service), и по
тем же правилам: мастер видит только свои сканы, опознаётся по коду Агбиса из
карточки, а отчёт берётся из прогретого кэша, а не считается на каждый запрос.
Отдельно от /masters (сводка по всем мастерам под правом payroll): здесь права
не нужны, потому что чужого сюда не попадает по построению — id берётся из
сессии, а не из запроса.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.services.access_control_service import ResolvedUser

from .dependencies import get_current_user

PERIODS = ("month", "prev_month")


def create_master_self_router() -> APIRouter:
    router = APIRouter(prefix="/masters/me", tags=["Masters"])

    def _master(current: ResolvedUser):
        from app.services.master_bot_service import resolve_master

        if not current.employee_id:
            raise HTTPException(status_code=403, detail="not_an_employee")
        master = resolve_master(current.employee_id)
        if master is None:
            raise HTTPException(status_code=404, detail="not_a_master")
        return master

    async def _run(fn, *args):
        from app.services.firebird_service import run_with_timeout
        from app.services.master_bot_service import StaleCacheError

        try:
            return await run_with_timeout(fn, *args, timeout=55)
        except StaleCacheError:
            raise HTTPException(
                status_code=503,
                detail="Данные обновляются, попробуйте через пару минут.",
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Сервер учёта сейчас занят, попробуйте через пару минут.",
            )

    @router.get("/earnings")
    async def get_my_earnings(
        period: str = Query("month"),
        current: ResolvedUser = Depends(get_current_user),
    ) -> dict:
        from app.services.master_bot_service import get_earnings

        if period not in PERIODS:
            raise HTTPException(status_code=400, detail="invalid_period")
        master = _master(current)
        report = await _run(get_earnings, master, period)
        return {**report, "name": master.name, "position": master.position}

    @router.get("/wip")
    async def get_my_wip(current: ResolvedUser = Depends(get_current_user)) -> dict:
        from app.services.master_bot_service import get_wip

        return {"items": await _run(get_wip, _master(current))}

    @router.get("/advance-cap")
    async def get_my_advance_cap(current: ResolvedUser = Depends(get_current_user)) -> dict:
        from app.services.master_bot_service import get_advance_cap

        return await _run(get_advance_cap, _master(current))

    return router
