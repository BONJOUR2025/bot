from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from app.schemas.message import (
    MessageRequest,
    BroadcastRequest,
    SentMessage,
    SentMessageSummary,
)
from app.services.telegram_service import (
    TelegramAPIError,
    TelegramNotConfiguredError,
    InvalidTelegramUserIdError,
    TelegramService,
)
from app.data.employee_repository import EmployeeRepository


SUCCESS_KEYWORDS = ("отправлено", "успеш", "принят", "достав", "sent", "accepted")
ERROR_KEYWORDS = ("ошиб", "error", "fail", "отклон")
INVALID_KEYWORDS = ("невалид", "invalid")
PENDING_KEYWORDS = ("ожид", "pending", "wait")


def _classify_status(value: Optional[str]) -> str:
    if not value:
        return "other"
    normalized = value.lower()
    if any(keyword in normalized for keyword in INVALID_KEYWORDS):
        return "invalid"
    if any(keyword in normalized for keyword in ERROR_KEYWORDS):
        return "errors"
    if any(keyword in normalized for keyword in PENDING_KEYWORDS):
        return "pending"
    if any(keyword in normalized for keyword in SUCCESS_KEYWORDS):
        return "success"
    return "other"


def _summarize_entry(entry: dict) -> Optional[dict[str, int]]:
    recipients = entry.get("recipients") or []
    counts = {
        "total": 0,
        "success": 0,
        "errors": 0,
        "invalid": 0,
        "pending": 0,
        "other": 0,
    }
    if entry.get("broadcast"):
        counts["total"] = len(recipients)
        for recipient in recipients:
            category = _classify_status(recipient.get("status"))
            counts[category] += 1
    else:
        status = entry.get("status")
        if status:
            counts["total"] = 1
            category = _classify_status(status)
            counts[category] += 1
    if counts["total"] == 0:
        return None
    return counts


def _format_summary_text(summary: SentMessageSummary | dict[str, int]) -> Optional[str]:
    if isinstance(summary, dict):
        summary = SentMessageSummary(**summary)
    if summary.total == 0:
        return None
    parts: list[str] = []
    if summary.success:
        parts.append(f"отправлено {summary.success}/{summary.total}")
    if summary.pending:
        parts.append(f"в ожидании {summary.pending}")
    if summary.errors:
        parts.append(f"ошибки {summary.errors}")
    if summary.invalid:
        parts.append(f"невалидные {summary.invalid}")
    if not parts and summary.other:
        parts.append(f"прочие {summary.other}")
    return " · ".join(parts) if parts else None


def _to_sent_message(entry: dict) -> SentMessage:
    data = dict(entry)
    summary = _summarize_entry(entry)
    if summary:
        data["summary"] = summary
        if entry.get("broadcast") and not entry.get("status"):
            status_text = _format_summary_text(summary)
            if status_text:
                data["status"] = status_text
    return SentMessage(**data)


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
        return [_to_sent_message(m) for m in service._load_log()]

    @router.delete("/sent_messages/{entry_id}")
    async def delete_sent_message(entry_id: str):
        service.delete_log_entry(entry_id)
        return {"status": "deleted"}

    return router
