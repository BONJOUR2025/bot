from fastapi import APIRouter, UploadFile, File, Response

from app.schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeOut
from app.services.employee_service import EmployeeAPIService
from app.services.pdf_profile import generate_employee_pdf
from app.data.payout_repository import PayoutRepository
from app.data.vacation_repository import VacationRepository


def create_employee_router(service: EmployeeAPIService) -> APIRouter:
    router = APIRouter(prefix="/employees", tags=["Employees"])

    @router.get("/", response_model=list[EmployeeOut])
    async def list_employees():
        return await service.list_employees()

    @router.post("/", response_model=EmployeeOut)
    async def create(data: EmployeeCreate):
        return await service.create_employee(data)

    @router.put("/{employee_id}", response_model=EmployeeOut)
    async def update(employee_id: str, data: EmployeeUpdate):
        return await service.update_employee(employee_id, data)

    @router.post("/{employee_id}/photo")
    async def upload_photo(employee_id: str, file: UploadFile = File(...)):
        return await service.upload_employee_photo(employee_id, file)

    @router.delete("/{employee_id}")
    async def delete(employee_id: str):
        return await service.delete_employee(employee_id)

    @router.get("/{user_id}/profile.pdf", response_class=Response)
    async def get_employee_profile_pdf(user_id: int):
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
    async def export_employees_pdf():
        pdf_bytes = await service.export_employees_pdf()
        headers = {"Content-Disposition": "inline; filename=employees.pdf"}
        return Response(content=pdf_bytes,
                        media_type="application/pdf",
                        headers=headers)

    return router
