from typing import Optional

from pydantic import BaseModel


class SalaryRow(BaseModel):
    employee_id: str
    name: str
    month: str
    base_salary: float = 0.0
    kpi_bonus: float = 0.0
    attendance_bonus: float = 0.0
    deductions: float = 0.0
    final_amount: float = 0.0
    comment: Optional[str] = None
