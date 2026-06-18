from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel

LeaveRequestType = Literal["Отгул", "Отпуск без содержания", "Больничный", "Другое"]
LeaveRequestStatus = Literal["Ожидает", "Одобрено", "Отклонено"]


class LeaveRequest(BaseModel):
    id: Optional[int] = None
    employee_id: str
    name: str
    type: LeaveRequestType
    start_date: str
    end_date: str
    comment: Optional[str] = ""
    status: LeaveRequestStatus = "Ожидает"
    created_at: Optional[datetime] = None


class LeaveRequestCreate(BaseModel):
    employee_id: str
    name: str
    type: LeaveRequestType
    start_date: str
    end_date: str
    comment: Optional[str] = ""


class LeaveRequestStatusUpdate(BaseModel):
    status: LeaveRequestStatus
