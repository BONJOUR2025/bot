from typing import Optional

from pydantic import BaseModel


class SalaryRow(BaseModel):
    employee_id: str
    name: str
    month: str
    amount: float
    comment: Optional[str] = None
