from typing import Optional

from pydantic import BaseModel

class MessageRequest(BaseModel):
    user_id: str
    message: str
    parse_mode: str = "HTML"
    photo_url: Optional[str] = None
    require_ack: bool = False


class BroadcastRequest(BaseModel):
    message: str
    parse_mode: str = "HTML"
    photo_url: Optional[str] = None


class SentMessage(BaseModel):
    user_id: str
    message: str
    status: str
    message_id: int
    timestamp: str
    photo_url: Optional[str] = None
    requires_ack: bool = False

