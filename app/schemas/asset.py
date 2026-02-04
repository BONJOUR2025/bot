from typing import Optional
from pydantic import BaseModel


class Asset(BaseModel):
    id: Optional[int] = None
    employee_id: str
    employee_name: str
    position: Optional[str] = ""
    item_name: str
    size: Optional[str] = ""
    quantity: int = 1
    issue_date: str
    return_date: Optional[str] = None
    service_life: Optional[int] = None


class AssetCreate(BaseModel):
    employee_id: str
    employee_name: str
    position: Optional[str] = ""
    item_name: str
    size: Optional[str] = ""
    quantity: int = 1
    issue_date: str
    return_date: Optional[str] = None
    service_life: Optional[int] = None


class AssetUpdate(BaseModel):
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    position: Optional[str] = None
    item_name: Optional[str] = None
    size: Optional[str] = None
    quantity: Optional[int] = None
    issue_date: Optional[str] = None
    return_date: Optional[str] = None
    service_life: Optional[int] = None

