from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class PayoutRequest:
    """Запрос выплаты."""

    user_id: str
    name: str
    phone: str
    bank: str
    amount: int
    method: str
    payout_type: Optional[str] = None
    status: str = "Ожидает"
    timestamp: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
