from typing import Optional
from pydantic import BaseModel

class Payout(BaseModel):
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

class PayoutUpdate(BaseModel):
    status: Optional[str] = None
