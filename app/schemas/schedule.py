from pydantic import BaseModel
from typing import Optional

class ScheduleRow(BaseModel):
    point: str
    short: str
    employee_id: Optional[str] = None
    name: Optional[str] = None
