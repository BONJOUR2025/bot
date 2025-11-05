from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List

from .enums import EmployeeStatus
from ..constants import PayoutStates as PayoutStates  # re-export for handlers


@dataclass
class Employee:
    """Employee information."""

    id: str
    name: str
    full_name: str
    phone: str
    position: str = ""
    is_admin: bool = False
    card_number: str = ""
    bank: str = ""
    work_place: str = ""
    clothing_size: str = ""
    birthdate: Optional[date] = None
    note: str = ""
    photo_url: str = ""
    status: EmployeeStatus = EmployeeStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    tags: List[str] = field(default_factory=list)
    payout_chat_key: Optional[str] = None
