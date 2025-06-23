from typing import Optional
from pydantic import BaseModel


class Adjustment(BaseModel):
    id: Optional[int] = None
    employee_id: str
    employee_name: str
    record_type: str  # 'Удержание' or 'Премия'
    reason: str
    amount: float
    date: str
    status: str
