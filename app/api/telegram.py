from datetime import datetime
from fastapi import APIRouter, HTTPException
from telegram import Bot

from app.config import TOKEN
from app.schemas.message import MessageRequest, BroadcastRequest
from app.services.telegram_service import TelegramService
from app.data.employee_repository import EmployeeRepository


def create_telegram_router(repo: EmployeeRepository) -> APIRouter:
    router = APIRouter(prefix="/telegram", tags=["Telegram"])
    service = TelegramService(repo)

    @router.post("/send_message")
    async def send_message(data: MessageRequest):
        bot = Bot(token=TOKEN)
        try:
            await bot.send_message(chat_id=data.user_id, text=data.message)
            return {"success": True, "sent_at": datetime.utcnow().isoformat()}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Ошибка отправки: {exc}")

    @router.post("/broadcast")
    async def broadcast(data: BroadcastRequest):
        try:
            result = await service.broadcast_message_to_all(
                data.message, parse_mode=data.parse_mode, photo_url=data.photo_url
            )
            return result
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Ошибка рассылки: {exc}")

    return router

