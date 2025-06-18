from fastapi import APIRouter, UploadFile, File

from app.schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeOut
from app.services.employee_service import EmployeeAPIService


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

    return router
