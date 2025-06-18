from typing import Optional, Literal
from pydantic import BaseModel


class Vacation(BaseModel):
    id: Optional[int] = None
    employee_id: str
    name: str
    start_date: str
    end_date: str
    type: Literal["Отпуск", "Больничный", "Командировка"]
    comment: Optional[str] = ""


class VacationCreate(BaseModel):
    employee_id: str
    name: str
    start_date: str
    end_date: str
    type: Literal["Отпуск", "Больничный", "Командировка"]
    comment: Optional[str] = ""


class VacationUpdate(BaseModel):
    employee_id: Optional[str] = None
    name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    type: Optional[Literal["Отпуск", "Больничный", "Командировка"]] = None
    comment: Optional[str] = None
