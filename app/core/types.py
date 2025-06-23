from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

from .enums import EmployeeStatus


@dataclass
class Employee:
    """Employee information."""

    id: str
    name: str
    full_name: str
    phone: str
    card_number: str = ""
    bank: str = ""
    birthdate: Optional[date] = None
    note: str = ""
    photo_url: str = ""
    status: EmployeeStatus = EmployeeStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
