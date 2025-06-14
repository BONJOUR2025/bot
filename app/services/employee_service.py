from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import HTTPException, UploadFile

from app.core.enums import EmployeeStatus
from app.core.types import Employee
from app.data.repository import Repository
from app.schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeOut


class EmployeeService:
    """Service to manage employee data."""

    def __init__(self, repo: Repository | None = None) -> None:
        self._repo = repo or Repository()
        self._employees: List[Employee] = self._repo.list_employees()
        self._counter = max((e.id for e in self._employees), default=0)

    def list_employees(self) -> List[Employee]:
        return list(self._employees)

    def add_employee(self, employee: Employee) -> Employee:
        self._counter += 1
        employee.id = self._counter
        self._employees.append(employee)
        self._repo.save_employees(self._employees)
        return employee

    def update_employee(self, employee_id: int, **updates) -> Optional[Employee]:
        emp = self.get_employee(employee_id)
        if not emp:
            return None
        for key, value in updates.items():
            if hasattr(emp, key) and value is not None:
                setattr(emp, key, value)
        self._repo.save_employees(self._employees)
        return emp

    def remove_employee(self, employee_id: int) -> None:
        self._employees = [e for e in self._employees if e.id != employee_id]
        self._repo.save_employees(self._employees)

    def get_employee(self, employee_id: int) -> Optional[Employee]:
        for emp in self._employees:
            if emp.id == employee_id:
                return emp
        return None


class EmployeeAPIService:
    """Adapter that uses EmployeeService for API operations."""

    def __init__(self, service: EmployeeService) -> None:
        self.service = service

    async def list_employees(self) -> list[EmployeeOut]:
        employees = self.service.list_employees()
        return [EmployeeOut(**e.__dict__) for e in employees]

    async def create_employee(self, data: EmployeeCreate) -> EmployeeOut:
        employee = Employee(
            id=0,
            full_name=data.full_name,
            phone=data.phone,
            card_number=data.card_number,
            bank=data.bank,
            birthdate=data.birthdate,
            note=data.note or "",
            photo_url=data.photo_url or "",
            status=EmployeeStatus(data.status),
        )
        created = self.service.add_employee(employee)
        return EmployeeOut(**created.__dict__)

    async def update_employee(self, employee_id: int, data: EmployeeUpdate) -> EmployeeOut:
        emp = self.service.update_employee(employee_id, **data.dict())
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        return EmployeeOut(**emp.__dict__)

    async def upload_employee_photo(self, employee_id: int, file: UploadFile) -> dict[str, str]:
        emp = self.service.get_employee(employee_id)
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        upload_path = Path(f"static/uploads/employees/{employee_id}.jpg")
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        with open(upload_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        self.service.update_employee(employee_id, photo_url="/" + str(upload_path))
        return {"status": "photo_uploaded", "url": "/" + str(upload_path)}

    async def delete_employee(self, employee_id: int) -> dict[str, str]:
        emp = self.service.get_employee(employee_id)
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        self.service.remove_employee(employee_id)
        return {"status": "deleted"}
