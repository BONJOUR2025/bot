from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class EmployeeBase(BaseModel):
    name: str
    full_name: str
    phone: str
    card_number: str
    bank: str
    birthdate: Optional[date]
    note: Optional[str]
    photo_url: Optional[str]
    status: str


class EmployeeCreate(EmployeeBase):
    id: str


class EmployeeUpdate(EmployeeBase):
    pass


class EmployeeOut(EmployeeBase):
    id: str
    created_at: datetime


class Employee(BaseModel):
    """Employee entry as stored in ``user.json``."""

    id: str
    name: str
    phone: str
    note: Optional[str] = None
    photo_url: Optional[str] = None
