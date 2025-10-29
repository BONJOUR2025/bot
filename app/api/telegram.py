from datetime import datetime
from fastapi import APIRouter, HTTPException
from app.schemas.message import MessageRequest, BroadcastRequest, SentMessage
from app.services.telegram_service import (
    TelegramAPIError,
    TelegramNotConfiguredError,
    InvalidTelegramUserIdError,
    TelegramService,
)
from app.data.employee_repository import EmployeeRepository


def create_telegram_router(repo: EmployeeRepository) -> APIRouter:
    router = APIRouter(prefix="/telegram", tags=["Telegram"])
    service = TelegramService(repo)

    @router.post("/send_message")
    async def send_message(data: MessageRequest):
        if service.bot is None:
            raise HTTPException(status_code=400, detail="Telegram token not configured")
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
        except InvalidTelegramUserIdError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "invalid_user_id",
                    "message": str(exc),
                },
            ) from exc
        except TelegramAPIError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "telegram_bad_request",
                    "message": str(exc),
                },
            ) from exc
        except TelegramNotConfiguredError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "telegram_not_configured",
                    "message": str(exc),
                },
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "unexpected_error",
                    "message": str(exc),
                },
            ) from exc

    @router.post("/broadcast")
    async def broadcast(data: BroadcastRequest):
        if service.bot is None:
            raise HTTPException(status_code=400, detail="Telegram token not configured")
        try:
            filters = {
                "status": data.status,
                "position": data.position,
                "birthday_today": data.birthday_today,
                "tags": data.tags,
            }
            result = await service.broadcast_message_to_all(
                data.message,
                parse_mode=data.parse_mode,
                photo_url=data.photo_url,
                filters=filters,
                test_user_id=data.test_user_id,
            )
            return result
        except TelegramNotConfiguredError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "telegram_not_configured",
                    "message": str(exc),
                },
            ) from exc
        except TelegramAPIError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "telegram_bad_request",
                    "message": str(exc),
                },
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "unexpected_error",
                    "message": str(exc),
                },
            ) from exc

    @router.get("/sent_messages", response_model=list[SentMessage])
    async def sent_messages() -> list[SentMessage]:
        return [SentMessage(**m) for m in service._load_log()]

    @router.delete("/sent_messages/{entry_id}")
    async def delete_sent_message(entry_id: str):
        service.delete_log_entry(entry_id)
        return {"status": "deleted"}

    return router
