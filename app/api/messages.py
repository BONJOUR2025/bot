from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional, List
from app.schemas.message import MessageRequest, MessageOut
from app.services.message_service import MessageService
from app.services.template_service import TemplateService


def create_message_router(service: MessageService, templates: TemplateService | None = None) -> APIRouter:
    router = APIRouter(prefix="/messages", tags=["Messages"])
    template_service = templates or TemplateService()

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

    @router.get("/templates")
    async def list_templates():
        return await template_service.list_templates()

    @router.post("/templates")
    async def create_template(name: str = Form(...), text: str = Form(...)):
        return await template_service.create_template(name, text)

    @router.delete("/templates/{tpl_id}")
    async def delete_template(tpl_id: str):
        await template_service.delete_template(tpl_id)
        return {"status": "deleted"}

    return router
