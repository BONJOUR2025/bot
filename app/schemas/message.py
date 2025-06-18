from typing import Optional
from pydantic import BaseModel


class MessageRequest(BaseModel):
    user_id: str
    message: str
    parse_mode: str = "HTML"
    require_ack: bool = False


class MessageOut(BaseModel):
    id: str
    user_id: str
    name: str
    text: str
    photo: Optional[str] = None
    status: str
    accepted: bool
    timestamp: str
    timestamp_accept: Optional[str] = None
    message_id: int


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
