from typing import Optional, List

from fastapi import APIRouter, Query

from app.schemas.salary import SalaryRow
from app.services.salary_service import SalaryService


def create_salary_router(service: SalaryService) -> APIRouter:
    router = APIRouter(prefix="/salary", tags=["Salary"])

    @router.get("/", response_model=List[SalaryRow])
    async def list_salary(
        month: Optional[str] = Query(None),
        employee_id: Optional[str] = Query(None),
    ):
        return await service.get_salary(month=month, employee_id=employee_id)

    @router.get("/months", response_model=List[str])
    async def list_months():
        return await service.list_months()

    return router
