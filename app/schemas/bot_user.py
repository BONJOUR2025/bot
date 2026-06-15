from typing import Optional
from pydantic import BaseModel


class BotUserOut(BaseModel):
    telegram_id: str
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None


class BotUserLinkRequest(BaseModel):
    employee_id: str
