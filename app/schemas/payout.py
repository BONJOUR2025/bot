from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Payout(BaseModel):
    id: Optional[int] = None
    user_id: str
    name: str
    phone: str
    card_number: Optional[str] = None
    bank: str
    amount: float
    method: str
    payout_type: str
    status: str
    timestamp: Optional[datetime] = None
    note: Optional[str] = None
    show_note_in_bot: bool = False
    force_notify_cashier: bool = False


class PayoutCreate(BaseModel):
    user_id: str
    name: str
    phone: str
    card_number: Optional[str] = None
    bank: str
    amount: float
    method: str
    payout_type: str
    sync_to_bot: bool = False
    note: Optional[str] = None
    show_note_in_bot: bool = False
    timestamp: Optional[datetime] = None
    force_notify_cashier: bool = False


class PayoutUpdate(BaseModel):
    user_id: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    card_number: Optional[str] = None
    bank: Optional[str] = None
    amount: Optional[float] = None
    method: Optional[str] = None
    payout_type: Optional[str] = None
    status: Optional[str] = None
    notify_user: Optional[bool] = None
    note: Optional[str] = None
    show_note_in_bot: Optional[bool] = None
    timestamp: Optional[datetime] = None
    force_notify_cashier: Optional[bool] = None


class PayoutControlItem(BaseModel):
    """Extended payout info for control dashboard."""

    id: str
    name: str
    amount: float
    date: Optional[str] = None
    status: str
    type: str
    method: str
    warnings: list[str] = []
    is_manual: bool = False
    is_employee_active: bool = True
    previous_requests_count: int = 0
    previous_total_month: float = 0.0
