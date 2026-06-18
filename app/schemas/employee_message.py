from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel

EmployeeMessageStatus = Literal["new", "read", "replied"]


class EmployeeMessage(BaseModel):
    id: Optional[int] = None
    employee_id: str
    name: str
    message: str
    status: EmployeeMessageStatus = "new"
    reply: Optional[str] = None
    created_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None


class EmployeeMessageCreate(BaseModel):
    employee_id: str
    name: str
    message: str


class EmployeeMessageReply(BaseModel):
    reply: str
