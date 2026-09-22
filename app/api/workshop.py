"""Цех — приложение старшего мастера (workshop_service). Только чтение Агбиса.

Под отдельным правом «workshop»: его выдают человеку в «Доступе», должность
при этом не важна — старшим мастером может быть и мастер, и руководитель
отдела пошива. Единственная запись здесь — ручная отметка дня обучения
ученика, та же, что в панели «Мастера», и она пишется в нашу базу, не в Агбис.
"""
from __future__ import annotations

import asyncio
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.access_control_service import ResolvedUser

from .dependencies import get_current_user, require_permission


class AttendanceMark(BaseModel):
    date: date
    note: str = ""


def create_workshop_router() -> APIRouter:
    router = APIRouter(
        prefix="/workshop",
        tags=["Workshop"],
        dependencies=[Depends(require_permission("workshop"))],
    )

    @router.get("/overview")
    async def overview(refresh: bool = Query(False)):
        from app.services.firebird_service import run_with_timeout
        from app.services.master_bot_service import StaleCacheError
        from app.services.workshop_service import get_overview

        try:
            return await run_with_timeout(get_overview, refresh, timeout=55)
        except StaleCacheError:
            raise HTTPException(503, "Данные обновляются, попробуйте через пару минут.")
        except asyncio.TimeoutError:
            raise HTTPException(504, "Сервер учёта сейчас занят, попробуйте через пару минут.")

    @router.post("/apprentices/{employee_id}/attendance")
    async def mark_apprentice(employee_id: str, data: AttendanceMark,
                              current: ResolvedUser = Depends(get_current_user)):
        """День обучения, которого нет на турникете (забыл пропуск, учился не в цеху)."""
        from app.data.apprentice_attendance_repository import get_apprentice_attendance_repository
        from app.data.employee_repository import EmployeeRepository
        from app.services.masters_service import APPRENTICE_POSITION
        from app.services.workshop_service import invalidate

        emp = EmployeeRepository().get_employee(employee_id)
        if emp is None:
            raise HTTPException(404, "Сотрудник не найден")
        if emp.position != APPRENTICE_POSITION:
            raise HTTPException(400, f"У сотрудника не должность «{APPRENTICE_POSITION}»")
        if data.date > date.today():
            raise HTTPException(400, "Нельзя отметить день, который ещё не наступил")
        author = getattr(current, "login", None) or getattr(current, "id", "workshop")
        rec = get_apprentice_attendance_repository().add_mark(
            employee_id, data.date, note=data.note.strip() or "отметил старший мастер", author=str(author),
        )
        invalidate()
        return rec

    return router
