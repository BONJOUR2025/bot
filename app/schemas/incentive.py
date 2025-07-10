from typing import Optional, Literal
from pydantic import BaseModel


class Incentive(BaseModel):
    id: Optional[int] = None
    employee_id: str
    name: str
    type: Literal["bonus", "penalty"]
    amount: float
    reason: str
    date: str
    added_by: str
    locked: bool = False


class IncentiveCreate(BaseModel):
    employee_id: str
    name: str
    type: Literal["bonus", "penalty"]
    amount: float
    reason: str
    date: str
    added_by: str


class IncentiveUpdate(BaseModel):
    employee_id: Optional[str] = None
    name: Optional[str] = None
    type: Optional[Literal["bonus", "penalty"]] = None
    amount: Optional[float] = None
    reason: Optional[str] = None
    date: Optional[str] = None
    added_by: Optional[str] = None
    locked: Optional[bool] = None
