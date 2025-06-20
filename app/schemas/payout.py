from typing import Optional
from pydantic import BaseModel


class Payout(BaseModel):
    id: Optional[int] = None
    user_id: str
    name: str
    phone: str
    bank: str
    amount: float
    method: str
    payout_type: str
    status: str
    timestamp: str


class PayoutCreate(BaseModel):
    user_id: str
    name: str
    phone: str
    bank: str
    amount: float
    method: str
    payout_type: str
    sync_to_bot: bool = False


class PayoutUpdate(BaseModel):
    user_id: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    bank: Optional[str] = None
    amount: Optional[float] = None
    method: Optional[str] = None
    payout_type: Optional[str] = None
    status: Optional[str] = None
