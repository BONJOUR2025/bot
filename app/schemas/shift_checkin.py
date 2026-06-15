from typing import Optional
from pydantic import BaseModel


class ShiftCheckin(BaseModel):
    id: int
    employee_id: str
    employee_name: str
    date: str
    point: Optional[str] = None
    point_short: Optional[str] = None
    salon_id: Optional[str] = None
    salon_name: Optional[str] = None
    sent_at: str
    expected_open_time: Optional[str] = None
    delay_minutes: Optional[int] = None
    penalty_amount: Optional[float] = None
    incentive_id: Optional[int] = None
    photo_path: Optional[str] = None
    no_schedule: bool = False
    manual: bool = False


class ShiftCheckinManualCreate(BaseModel):
    employee_id: str
    employee_name: str
    date: str
    time: str
