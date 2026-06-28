from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class EmployeeBase(BaseModel):
    name: str
    full_name: Optional[str] = ""
    phone: Optional[str] = ""
    position: Optional[str] = ""
    is_admin: bool = False
    bot_user: bool = False
    card_number: Optional[str] = ""
    bank: Optional[str] = ""
    work_place: Optional[str] = ""
    clothing_size: Optional[str] = ""
    birthdate: Optional[date] = None
    note: Optional[str] = ""
    photo_url: Optional[str] = ""
    status: str = "active"
    payout_chat_key: Optional[str] = None
    archived: bool = False
    archived_at: Optional[datetime] = None
    passport_url: str = ""
    external_code: str = ""
    amo_user_id: Optional[str] = ""   # amoCRM responsible_user_id (для ЗП менеджеров)


class EmployeeCreate(EmployeeBase):
    id: Optional[str] = ""


class EmployeeUpdate(EmployeeBase):
    id: Optional[str] = None


class EmployeeSelfUpdate(BaseModel):
    """Subset of fields an employee may edit about themselves."""

    phone: Optional[str] = None
    card_number: Optional[str] = None
    bank: Optional[str] = None


class EmployeeOut(EmployeeBase):
    id: str
    created_at: datetime
    archived: bool = False
    archived_at: Optional[datetime] = None


class Employee(BaseModel):
    """Employee entry as stored in ``user.json``."""

    id: str
    name: str
    phone: str
    position: str = ""
    work_place: str = ""
    clothing_size: str = ""
    is_admin: bool = False
    bot_user: bool = False
    note: Optional[str] = None
    photo_url: Optional[str] = None
    payout_chat_key: Optional[str] = None
    archived: bool = False
