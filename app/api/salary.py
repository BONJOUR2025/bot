from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.schemas.salary import SalaryRow
from app.services.salary_service import SalaryService
from app.services.access_control_service import AccessControlService, ResolvedUser

from .dependencies import get_current_user


def create_salary_router(
    service: SalaryService, access_service: AccessControlService
) -> APIRouter:
    router = APIRouter(prefix="/salary", tags=["Salary"])

    def _filter_salary(rows: List[SalaryRow], current: ResolvedUser) -> List[SalaryRow]:
        allowed = access_service.visible_employee_ids(current)
        if allowed is None:
            return rows
        return [row for row in rows if str(row.employee_id) in allowed]

    @router.get("/", response_model=List[SalaryRow])
    async def list_salary(
        month: Optional[str] = Query(None),
        employee_id: Optional[str] = Query(None),
        current: ResolvedUser = Depends(get_current_user),
    ):
        allowed = access_service.visible_employee_ids(current)
        if allowed is not None and employee_id and employee_id not in allowed:
            return []
        rows = await service.get_salary(month=month, employee_id=employee_id)
        return _filter_salary(rows, current)

    @router.get("/months", response_model=List[str])
    async def list_months():
        return await service.list_months()

    @router.get("/report", response_class=Response)
    async def salary_report(
        month: str = Query(...), current: ResolvedUser = Depends(get_current_user)
    ):
        allowed = access_service.visible_employee_ids(current)
        if allowed is not None:
            raise HTTPException(status_code=403, detail="forbidden")
        rows = await service.get_salary(month=month)
        from app.services.salary_report import generate_salary_pdf

        pdf_bytes = generate_salary_pdf(rows, month)
        headers = {"Content-Disposition": "inline; filename=salary_report.pdf"}
        return Response(content=pdf_bytes,
                        media_type="application/pdf",
                        headers=headers)

    return router
