from pydantic import BaseModel

class MessageRequest(BaseModel):
    user_id: str
    message: str

