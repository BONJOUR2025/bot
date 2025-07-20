from fastapi import APIRouter, HTTPException, Query, Body

from app.schemas.uniform import Uniform, UniformCreate, UniformUpdate
from app.services.uniform_service import UniformService
from app.services.employee_service import EmployeeService


def create_uniform_router(service: UniformService, employee_service: EmployeeService) -> APIRouter:
    router = APIRouter(prefix="/uniforms", tags=["Uniforms"])

    @router.get("/", response_model=list[Uniform])
    async def list_uniforms(employee_id: str | None = Query(None)):
        return await service.list_uniforms(employee_id)

    @router.post("/", response_model=Uniform)
    async def create_uniform(data: UniformCreate):
        return await service.create_uniform(data)

    @router.put("/{item_id}", response_model=Uniform)
    async def update_uniform(item_id: str, data: UniformUpdate):
        uniform = await service.update_uniform(item_id, data)
        if not uniform:
            raise HTTPException(status_code=404, detail="Not found")
        return uniform

    @router.delete("/{item_id}")
    async def delete_uniform(item_id: str):
        await service.delete_uniform(item_id)
        return {"status": "deleted"}

    @router.post("/kit")
    async def create_kit(employee_ids: list[str] = Body(...)):
        employees = [employee_service.service.get_employee(eid) for eid in employee_ids]
        employees = [e for e in employees if e]
        return await service.calculate_kit(employees)

    return router
