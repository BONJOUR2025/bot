from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class Payout(BaseModel):
    id: str
    user_id: str
    name: str
    amount: float
    type: str
    method: str
    status: str
    created_at: datetime
    comment: Optional[str] = None

class PayoutCreate(BaseModel):
    user_id: str
    name: str
    amount: float
    type: str
    method: str
    comment: Optional[str] = None

class PayoutUpdate(BaseModel):
    status: Optional[str] = None
    comment: Optional[str] = None
