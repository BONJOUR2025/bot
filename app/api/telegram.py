from datetime import datetime
from fastapi import APIRouter, HTTPException
from app.schemas.message import MessageRequest, BroadcastRequest, SentMessage
from app.services.telegram_service import TelegramService
from app.data.employee_repository import EmployeeRepository


def create_telegram_router(repo: EmployeeRepository) -> APIRouter:
    router = APIRouter(prefix="/telegram", tags=["Telegram"])
    service = TelegramService(repo)

    @router.post("/send_message")
    async def send_message(data: MessageRequest):
        try:
            message_id = await service.send_message_to_user(
                data.user_id,
                data.message,
                parse_mode=data.parse_mode,
                photo_url=data.photo_url,
                require_ack=data.require_ack,
            )
            return {
                "success": True,
                "sent_at": datetime.utcnow().isoformat(),
                "message_id": message_id,
            }
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Ошибка отправки: {exc}")

    @router.post("/broadcast")
    async def broadcast(data: BroadcastRequest):
        try:
            result = await service.broadcast_message_to_all(
                data.message, parse_mode=data.parse_mode, photo_url=data.photo_url
            )
            return result
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Ошибка рассылки: {exc}")

    @router.get("/sent_messages", response_model=list[SentMessage])
    async def sent_messages() -> list[SentMessage]:
        return [SentMessage(**m) for m in service._load_log()]

    return router
