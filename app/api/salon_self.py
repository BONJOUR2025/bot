"""Кабинет администратора точки — в приложении «BONJOUR Салон».

Приложение задумано как личный кабинет с тем же набором, что кнопки бота:
зарплата, график, авансы, история, имущество, профиль. Рабочих инструментов
точки (выручка, заказы клиентов) здесь нет намеренно — они остаются в панели.

Ровно как /masters/me (master_self): прав не нужно, потому что чужого сюда не
попадает по построению — точка берётся из карточки сотрудника по сессии, а не
из запроса.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

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

    def _employee_name(current: ResolvedUser) -> str:
        """Имя, под которым сотрудник стоит в графике (карточка, поле name)."""
        from app.data.employee_repository import EmployeeRepository

        employee = EmployeeRepository().get_employee(str(current.employee_id))
        return ((employee.name if employee else "") or current.display_name or "").strip()

    @router.get("/shifts")
    async def my_shifts(
        year: int = Query(None), month: int = Query(None),
        current: ResolvedUser = Depends(get_current_user),
    ) -> dict:
        """Мои смены за месяц и ссылка на файл календаря.

        Ссылку открывает внешний браузер (во WebView скачивания нет), поэтому
        в ней своя короткоживущая метка, а не сессия кабинета.
        """
        from app.services import shift_calendar_service as cal

        if not current.employee_id:
            raise HTTPException(status_code=403, detail="not_an_employee")
        today = date.today()
        year, month = int(year or today.year), int(month or today.month)
        if not 1 <= month <= 12:
            raise HTTPException(status_code=400, detail="bad_month")
        name = _employee_name(current)
        shifts = await cal.shifts_for(name, year, month)
        token = cal.make_token(current.id)
        return {
            "year": year, "month": month, "count": len(shifts),
            "next": cal.next_shift(shifts),
            "days": [{"date": s.day.isoformat(), "point": s.point_name,
                      "start": s.start, "end": s.end} for s in shifts],
            "ics_url": f"/api/salon/shifts/{token}.ics?year={year}&month={month}",
        }

    @router.get("/assets")
    async def my_assets(current: ResolvedUser = Depends(get_current_user)) -> dict:
        """Что за мной числится: форма, инструмент, техника."""
        from app.services.salon_self_service import assets

        if not current.employee_id:
            raise HTTPException(status_code=403, detail="not_an_employee")
        return {"items": assets(str(current.employee_id))}

    return router


def create_salon_ics_router() -> APIRouter:
    """Файл календаря по подписанной ссылке — без сессии кабинета.

    Отдельный роутер, потому что подключается вне «только после входа»:
    открывает ссылку внешний браузер, у которого сессии нет. Метка в адресе
    живёт минуты и открывает ровно один файл — свои смены за месяц.
    """
    router = APIRouter(prefix="/salon/shifts", tags=["SalonSelf"])

    @router.get("/{token}.ics", response_class=PlainTextResponse, include_in_schema=False)
    async def shifts_ics(token: str, year: int = Query(...), month: int = Query(...)):
        from app.services import shift_calendar_service as cal
        from app.services.access_control_service import get_access_control_service
        from app.data.employee_repository import EmployeeRepository

        try:
            user_id = cal.read_token(token)
        except cal.BadToken:
            raise HTTPException(status_code=403, detail="Ссылка устарела — откройте «График» ещё раз.")
        user = get_access_control_service().resolve_user(user_id)
        if user is None or not user.employee_id:
            raise HTTPException(status_code=403, detail="Ссылка устарела — откройте «График» ещё раз.")
        employee = EmployeeRepository().get_employee(str(user.employee_id))
        name = ((employee.name if employee else "") or user.display_name or "").strip()
        shifts = await cal.shifts_for(name, int(year), int(month))
        body = cal.build_ics(shifts, name, int(year), int(month))
        return PlainTextResponse(
            body,
            media_type="text/calendar; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="bonjour-shifts-{year}-{month:02d}.ics"',
                # Как у APK: GZipMiddleware не должен трогать файл, который
                # телефон отдаёт календарю.
                "Content-Encoding": "identity",
            },
        )

    return router
