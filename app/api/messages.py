from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional, List
from app.schemas.message import MessageRequest, MessageOut
from app.services.message_service import MessageService


def create_message_router(service: MessageService) -> APIRouter:
    router = APIRouter(prefix="/messages", tags=["Messages"])

    @router.get("/", response_model=List[MessageOut])
    async def list_messages() -> List[MessageOut]:
        return await service.list_messages()

    @router.post("/", response_model=MessageOut)
    async def send_message(
        user_id: str = Form(...),
        message: str = Form(...),
        parse_mode: str = Form("HTML"),
        require_ack: bool = Form(False),
        photo: Optional[UploadFile] = File(None),
    ) -> MessageOut:
        data = MessageRequest(
            user_id=user_id,
            message=message,
            parse_mode=parse_mode,
            require_ack=require_ack)
        # photo handling not yet stored
        return await service.send_message(data)

    @router.post("/{message_id}/accept", response_model=MessageOut)
    async def accept_message(message_id: str) -> MessageOut:
        msg = await service.accept_message(message_id)
        if not msg:
            raise HTTPException(status_code=404, detail="Not found")
        return msg

    return router
