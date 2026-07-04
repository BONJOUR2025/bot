from typing import Optional
from pydantic import BaseModel


class VkBotUserOut(BaseModel):
    vk_id: str
    screen_name: str = ""
    first_name: str = ""
    last_name: str = ""
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None


class VkBotUserLinkRequest(BaseModel):
    employee_id: str
