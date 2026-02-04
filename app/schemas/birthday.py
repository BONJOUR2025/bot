from datetime import date
from typing import Optional

from pydantic import BaseModel


class Birthday(BaseModel):
    user_id: str
    full_name: str
    birthdate: date
    phone: Optional[str] = ""
