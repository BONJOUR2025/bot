"""Кабинет администратора точки — в приложении «BONJOUR Салон».

Приложение задумано как личный кабинет с тем же набором, что кнопки бота:
зарплата, график, авансы, история, имущество, профиль. Рабочих инструментов
точки (выручка, заказы клиентов) здесь нет намеренно — они остаются в панели.

Ровно как /masters/me (master_self): прав не нужно, потому что чужого сюда не
попадает по построению — точка берётся из карточки сотрудника по сессии, а не
из запроса.
"""
from __future__ import annotations

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

    @router.get("/assets")
    async def my_assets(current: ResolvedUser = Depends(get_current_user)) -> dict:
        """Что за мной числится: форма, инструмент, техника."""
        from app.services.salon_self_service import assets

        if not current.employee_id:
            raise HTTPException(status_code=403, detail="not_an_employee")
        return {"items": assets(str(current.employee_id))}

    return router
