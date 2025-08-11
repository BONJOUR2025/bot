from typing import Optional, List

from fastapi import APIRouter, Query, Response

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

    @router.get("/report", response_class=Response)
    async def salary_report(month: str = Query(...)):
        rows = await service.get_salary(month=month)
        from app.services.salary_report import generate_salary_pdf

        pdf_bytes = generate_salary_pdf(rows, month)
        headers = {"Content-Disposition": "inline; filename=salary_report.pdf"}
        return Response(content=pdf_bytes,
                        media_type="application/pdf",
                        headers=headers)

    return router
