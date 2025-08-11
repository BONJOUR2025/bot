from typing import Optional, List, Union
from pydantic import BaseModel


class MessageRequest(BaseModel):
    user_id: str
    message: str
    parse_mode: str = "HTML"
    require_ack: bool = False
    photo_url: Optional[str] = None


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
    status: Optional[str | list[str]] = None
    position: Optional[str | list[str]] = None
    birthday_today: bool = False
    tags: Optional[list[str]] = None
    test_user_id: Optional[str] = None


class SentMessage(BaseModel):
    id: str
    user_id: Optional[str] = None
    message: str
    status: str
    message_id: Optional[int] = None
    timestamp: str
    photo_url: Optional[str] = None
    requires_ack: bool = False
    broadcast: bool = False
    recipients: Optional[list[dict]] = None
