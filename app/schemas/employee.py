from datetime import date
from typing import Optional

from pydantic import BaseModel


class EmployeeBase(BaseModel):
    full_name: str
    phone: str
    card_number: str
    bank: str
    birthdate: Optional[date]
    note: Optional[str]
    photo_url: Optional[str]
    status: str


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(EmployeeBase):
    pass


class EmployeeOut(EmployeeBase):
    id: int
    created_at: str
