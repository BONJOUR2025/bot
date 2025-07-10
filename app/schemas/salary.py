from typing import Optional

from pydantic import BaseModel


class SalaryRow(BaseModel):
    employee_id: str
    name: str
    month: str
    shifts_main: int = 0
    shifts_extra: int = 0
    shifts_total: int = 0
    salary_fixed: float = 0.0
    salary_repair: float = 0.0
    salary_cosmetics: float = 0.0
    salary_shoes: float = 0.0
    salary_accessories: float = 0.0
    salary_keys: float = 0.0
    salary_slippers: float = 0.0
    salary_workshop: float = 0.0
    salary_bonus: float = 0.0
    salary_total: float = 0.0
    deduction: float = 0.0
    advance: float = 0.0
    final_amount: float = 0.0
    comment: Optional[str] = None
