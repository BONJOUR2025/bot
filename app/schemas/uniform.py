from typing import Optional
from pydantic import BaseModel


class Uniform(BaseModel):
    id: Optional[int] = None
    employee_id: str
    name: str
    item: str
    size: Optional[str] = ""
    quantity: int = 1
    issue_date: str
    return_date: Optional[str] = None
    comment: Optional[str] = ""


class UniformCreate(BaseModel):
    employee_id: str
    name: str
    item: str
    size: Optional[str] = ""
    quantity: int = 1
    issue_date: str
    return_date: Optional[str] = None
    comment: Optional[str] = ""


class UniformUpdate(BaseModel):
    employee_id: Optional[str] = None
    name: Optional[str] = None
    item: Optional[str] = None
    size: Optional[str] = None
    quantity: Optional[int] = None
    issue_date: Optional[str] = None
    return_date: Optional[str] = None
    comment: Optional[str] = None
