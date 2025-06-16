from datetime import datetime
from fastapi import APIRouter, HTTPException
from telegram import Bot

from app.config import TOKEN
from app.schemas.message import MessageRequest


def create_telegram_router() -> APIRouter:
    router = APIRouter(prefix="/telegram", tags=["Telegram"])

    @router.post("/send_message")
    async def send_message(data: MessageRequest):
        bot = Bot(token=TOKEN)
        try:
            await bot.send_message(chat_id=data.user_id, text=data.message)
            return {"success": True, "sent_at": datetime.utcnow().isoformat()}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Ошибка отправки: {exc}")

    return router

