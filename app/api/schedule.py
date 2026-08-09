import asyncio
from datetime import date as date_cls
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.dependencies import require_permission
from app.schemas.schedule import SchedulePointOut
from app.services.schedule_service import ScheduleService


class ScheduleCellUpdate(BaseModel):
    year: int
    month: int
    employee: str
    day: int
    code: Optional[str] = ""


def create_schedule_router(service: ScheduleService) -> APIRouter:
    router = APIRouter(prefix="/schedule", tags=["Schedule"])

    @router.get("/by_day", response_model=List[SchedulePointOut])
    async def schedule_by_day(date: str = Query(...)):
        return await service.get_schedule_by_day(date)

    @router.get("/month")
    async def schedule_month(year: int = Query(...), month: int = Query(...)):
        if not (1 <= month <= 12):
            raise HTTPException(status_code=400, detail="month must be 1–12")
        return await service.get_schedule_month(year, month)

    # Право то же, что и на саму правку: фронтенд использует этот запрос как
    # пробу «могу ли я редактировать». Без проверки сотрудник получал бы
    # редактируемые клетки и отказ лишь после выбора кода.
    @router.get("/codes", dependencies=[Depends(require_permission("payroll"))])
    def schedule_codes():
        """Коды салонов для выпадающего списка в клетке расписания."""
        from app.data.salon_repository import get_salon_repository

        return [
            {"code": s.code, "name": s.name}
            for s in get_salon_repository().list_salons() if s.code
        ]

    # Просмотр графика открыт всем сотрудникам, а правка — нет: она пишет в
    # тот же файл, где лежит ФОТ, и меняет исходные данные для расчёта
    # зарплаты. Право «payroll» есть только у владельца.
    @router.patch("/cell", dependencies=[Depends(require_permission("payroll"))])
    async def update_schedule_cell(data: ScheduleCellUpdate):
        """Проставить код салона в клетку графика.

        Пишет в тот же файл, что и ФОТ, через настоящий Excel — иначе
        пересчитываемые от графика формулы зарплаты обнулились бы. Подробности
        и замеры в app/services/schedule_editor.py.
        """
        from app.services.schedule_editor import ScheduleEditError, set_schedule_cell

        if not (1 <= data.month <= 12):
            raise HTTPException(status_code=400, detail="month must be 1–12")

        try:
            # Excel COM блокирует поток на время правки, поэтому уводим его в
            # пул — иначе на время сохранения встаёт весь event loop API.
            return await asyncio.to_thread(
                set_schedule_cell, data.year, data.month,
                data.employee, data.day, data.code or "",
            )
        except ScheduleEditError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Не удалось сохранить график: {exc}")

    return router
