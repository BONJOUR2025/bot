"""Кабинет администратора точки — в приложении «BONJOUR Салон».

Ровно как /masters/me (master_self): прав не нужно, потому что чужого сюда не
попадает по построению — точка берётся из карточки сотрудника по сессии, а не
из запроса. Все обращения к Агбису идут через run_with_timeout: заказы и
выручка живут в самом дорогом месте системы, и висящий запрос с телефона не
должен занимать соединение бесконечно.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.services.access_control_service import ResolvedUser

from .dependencies import get_current_user


def create_salon_self_router() -> APIRouter:
    router = APIRouter(prefix="/salon/me", tags=["SalonSelf"])

    def _point(current: ResolvedUser):
        from app.services.salon_self_service import resolve_point

        if not current.employee_id:
            raise HTTPException(status_code=403, detail="not_an_employee")
        point = resolve_point(current.employee_id)
        if point is None:
            raise HTTPException(status_code=404, detail="not_on_a_point")
        return point

    async def _run(fn, *args):
        from app.services.firebird_service import run_with_timeout

        try:
            return await run_with_timeout(fn, *args, timeout=55)
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Сервер учёта сейчас занят, попробуйте через пару минут.",
            )

    @router.get("/point")
    async def my_point(current: ResolvedUser = Depends(get_current_user)) -> dict:
        """Моя точка и сегодняшняя отметка об открытии смены."""
        from app.services.salon_self_service import shift_today

        point = _point(current)
        return {
            "point": point.to_dict(),
            "shift": shift_today(str(current.employee_id), point),
            "name": current.display_name,
        }

    @router.get("/sales")
    async def my_sales(current: ResolvedUser = Depends(get_current_user)) -> dict:
        """Выручка точки: сегодня, вчера, с начала месяца и по дням."""
        from app.services.salon_self_service import sales

        return await _run(sales, _point(current))

    @router.get("/orders")
    async def my_orders(current: ResolvedUser = Depends(get_current_user)) -> dict:
        """Невыданные заказы точки: готовые к выдаче и горящие — сверху."""
        from app.services.salon_self_service import orders

        return await _run(orders, _point(current))

    @router.get("/assets")
    async def my_assets(current: ResolvedUser = Depends(get_current_user)) -> dict:
        """Что за мной числится: форма, инструмент, техника."""
        from app.services.salon_self_service import assets

        if not current.employee_id:
            raise HTTPException(status_code=403, detail="not_an_employee")
        return {"items": assets(str(current.employee_id))}

    return router
