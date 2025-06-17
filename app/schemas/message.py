from typing import Optional

from pydantic import BaseModel

class MessageRequest(BaseModel):
    user_id: str
    message: str


class BroadcastRequest(BaseModel):
    message: str
    parse_mode: str = "HTML"
    photo_url: Optional[str] = None

