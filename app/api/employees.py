from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from app.schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeOut
from app.services.employee_service import EmployeeAPIService
from app.services.pdf_profile import generate_employee_pdf
from app.data.payout_repository import PayoutRepository
from app.data.vacation_repository import VacationRepository
from app.services.access_control_service import AccessControlService, ResolvedUser

from .dependencies import get_current_user


def create_employee_router(
    service: EmployeeAPIService, access_service: AccessControlService
) -> APIRouter:
    router = APIRouter(prefix="/employees", tags=["Employees"])

    def _employee_department(employee_id: str) -> str | None:
        employee = service.service.get_employee(employee_id)
        return employee.work_place if employee else None

    @router.get("/", response_model=list[EmployeeOut])
    async def list_employees(current: ResolvedUser = Depends(get_current_user)):
        employees = await service.list_employees()
        return [
            employee
            for employee in employees
            if access_service.is_employee_visible(
                current, employee.id, employee.work_place
            )
        ]

    @router.post("/", response_model=EmployeeOut)
    async def create(
        data: EmployeeCreate, current: ResolvedUser = Depends(get_current_user)
    ):
        if access_service.user_employee_scope(current) or access_service.user_department_scope(
            current
        ):
            raise HTTPException(status_code=403, detail="forbidden")
        return await service.create_employee(data)

    @router.put("/{employee_id}", response_model=EmployeeOut)
    async def update(
        employee_id: str,
        data: EmployeeUpdate,
        current: ResolvedUser = Depends(get_current_user),
    ):
        if not access_service.is_employee_visible(
            current, employee_id, _employee_department(employee_id)
        ):
            raise HTTPException(status_code=403, detail="forbidden")
        return await service.update_employee(employee_id, data)

    @router.post("/{employee_id}/photo")
    async def upload_photo(
        employee_id: str,
        file: UploadFile = File(...),
        current: ResolvedUser = Depends(get_current_user),
    ):
        if not access_service.is_employee_visible(
            current, employee_id, _employee_department(employee_id)
        ):
            raise HTTPException(status_code=403, detail="forbidden")
        return await service.upload_employee_photo(employee_id, file)

    @router.delete("/{employee_id}")
    async def delete(
        employee_id: str, current: ResolvedUser = Depends(get_current_user)
    ):
        if not access_service.is_employee_visible(
            current, employee_id, _employee_department(employee_id)
        ):
            raise HTTPException(status_code=403, detail="forbidden")
        return await service.delete_employee(employee_id)

    @router.get("/{user_id}/profile.pdf", response_class=Response)
    async def get_employee_profile_pdf(
        user_id: int, current: ResolvedUser = Depends(get_current_user)
    ):
        if not access_service.is_employee_visible(
            current, str(user_id), _employee_department(str(user_id))
        ):
            raise HTTPException(status_code=403, detail="forbidden")
        pdf_bytes = generate_employee_pdf(
            user_id,
            employee_repo=service.service._repo,
            payout_repo=PayoutRepository(),
            vacation_repo=VacationRepository(),
        )
        headers = {"Content-Disposition": "inline; filename=profile.pdf"}
        return Response(content=pdf_bytes,
                        media_type="application/pdf",
                        headers=headers)

    @router.get("/export.pdf", response_class=Response)
    async def export_employees_pdf(
        current: ResolvedUser = Depends(get_current_user),
    ):
        if access_service.user_employee_scope(current) or access_service.user_department_scope(
            current
        ):
            raise HTTPException(status_code=403, detail="forbidden")
        pdf_bytes = await service.export_employees_pdf()
        headers = {"Content-Disposition": "inline; filename=employees.pdf"}
        return Response(content=pdf_bytes,
                        media_type="application/pdf",
                        headers=headers)

    return router
