from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import HTTPException, UploadFile

from app.core.enums import EmployeeStatus
from app.core.types import Employee
from app.data.employee_repository import EmployeeRepository
from app.schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeOut


class EmployeeService:
    """Service to manage employee data."""

    def __init__(self, repo: EmployeeRepository | None = None) -> None:
        self._repo = repo or EmployeeRepository()
        self._employees: List[Employee] = self._repo.list_employees(archived=None)
        self._counter = max(
            (int(
                e.id) for e in self._employees if str(
                e.id).isdigit()),
            default=0)

    def list_employees(self, archived: bool | None = False) -> List[Employee]:
        if archived is None:
            return list(self._employees)
        return [
            emp for emp in self._employees if getattr(emp, "archived", False) == archived
        ]

    def add_employee(self, employee: Employee) -> Employee:
        if not employee.id:
            self._counter += 1
            employee.id = str(self._counter)
        else:
            # keep counter in sync if numeric ids are provided
            if str(employee.id).isdigit():
                self._counter = max(self._counter, int(employee.id))
        if any(e.id == str(employee.id) for e in self._employees):
            raise ValueError("employee_exists")
        if not hasattr(employee, "archived"):
            employee.archived = False
        self._employees.append(employee)
        self._repo.add_employee(employee)
        return employee

    def update_employee(
            self,
            employee_id: str,
            **updates) -> Optional[Employee]:
        emp = self.get_employee(employee_id)
        if not emp:
            return None
        new_id = updates.pop("id", None)
        for key, value in updates.items():
            if hasattr(emp, key):
                setattr(emp, key, value)
        if new_id and new_id != emp.id:
            if any(e.id == str(new_id) for e in self._employees):
                raise ValueError("employee_exists")
            self._repo.delete_employee_by_id(emp.id)
            emp.id = str(new_id)
            if str(emp.id).isdigit():
                self._counter = max(self._counter, int(emp.id))
            self._repo.add_employee(emp)
        else:
            self._repo.update_employee(emp)
        return emp

    def archive_employee(self, employee_id: str) -> Optional[Employee]:
        emp = self.get_employee(employee_id)
        if not emp:
            return None
        if emp.status != EmployeeStatus.INACTIVE:
            raise ValueError("employee_not_inactive")
        if getattr(emp, "archived", False):
            return emp
        emp.archived = True
        emp.archived_at = datetime.utcnow()
        self._repo.update_employee(emp)
        return emp

    def restore_employee(self, employee_id: str) -> Optional[Employee]:
        emp = self.get_employee(employee_id)
        if not emp:
            return None
        if not getattr(emp, "archived", False):
            return emp
        emp.archived = False
        emp.archived_at = None
        self._repo.update_employee(emp)
        return emp

    def remove_employee(self, employee_id: str) -> None:
        self._employees = [e for e in self._employees if e.id != employee_id]
        self._repo.delete_employee_by_id(employee_id)

    def get_employee(self, employee_id: str) -> Optional[Employee]:
        for emp in self._employees:
            if emp.id == employee_id:
                return emp
        return None


class EmployeeAPIService:
    """Adapter that uses EmployeeService for API operations."""

    def __init__(self, service: EmployeeService) -> None:
        self.service = service

    async def list_employees(self, archived: bool | None = False) -> list[EmployeeOut]:
        employees = self.service.list_employees(archived=archived)
        return [EmployeeOut(**e.__dict__) for e in employees]

    async def create_employee(self, data: EmployeeCreate) -> EmployeeOut:
        employee = Employee(
            id=data.id or "",
            name=data.name,
            full_name=data.full_name or "",
            phone=data.phone or "",
            position=data.position or "",
            is_admin=data.is_admin or False,
            card_number=data.card_number or "",
            bank=data.bank or "",
            work_place=data.work_place or "",
            clothing_size=data.clothing_size or "",
            birthdate=data.birthdate,
            note=data.note or "",
            photo_url=data.photo_url or "",
            status=EmployeeStatus(data.status or "active"),
            payout_chat_key=data.payout_chat_key,
            archived=data.archived,
            archived_at=data.archived_at,
        )
        try:
            created = self.service.add_employee(employee)
        except ValueError:
            raise HTTPException(status_code=400, detail="Employee already exists")
        return EmployeeOut(**created.__dict__)

    async def update_employee(
            self,
            employee_id: str,
            data: EmployeeUpdate) -> EmployeeOut:
        try:
            emp = self.service.update_employee(
                employee_id, **data.dict(exclude_unset=True)
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Employee already exists")
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        return EmployeeOut(**emp.__dict__)

    async def archive_employee(self, employee_id: str) -> EmployeeOut:
        try:
            emp = self.service.archive_employee(employee_id)
        except ValueError as exc:
            if str(exc) == "employee_not_inactive":
                raise HTTPException(status_code=400, detail="only_inactive_can_be_archived")
            raise
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        return EmployeeOut(**emp.__dict__)

    async def restore_employee(self, employee_id: str) -> EmployeeOut:
        emp = self.service.restore_employee(employee_id)
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        return EmployeeOut(**emp.__dict__)

    async def upload_employee_photo(
            self, employee_id: str, file: UploadFile) -> dict[str, str]:
        emp = self.service.get_employee(employee_id)
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        upload_path = Path(f"static/uploads/employees/{employee_id}.jpg")
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        with open(upload_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        self.service.update_employee(
            employee_id, photo_url="/" + str(upload_path))
        return {"status": "photo_uploaded", "url": "/" + str(upload_path)}

    async def delete_employee(self, employee_id: str) -> dict[str, str]:
        emp = self.service.get_employee(employee_id)
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        self.service.remove_employee(employee_id)
        return {"status": "deleted"}

    async def export_employees_pdf(self) -> bytes:
        employees = self.service.list_employees()
        from app.services.pdf_profile import generate_employees_list_pdf

        return generate_employees_list_pdf(employees)
