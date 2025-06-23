from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    """Модель данных пользователя."""

    user_id: str
    name: str
    phone: str
    bank: str
    birthday: Optional[str] = None
