from datetime import datetime
from typing import List, Optional

from app.schemas.message import MessageRequest, MessageOut
from app.data.message_repository import MessageRepository
from app.data.employee_repository import EmployeeRepository
from .telegram_service import TelegramService


class MessageService:
    def __init__(
            self,
            repo: Optional[MessageRepository] = None,
            employee_repo: Optional[EmployeeRepository] = None) -> None:
        self._repo = repo or MessageRepository()
        self._employees = employee_repo or EmployeeRepository()
        self._telegram = TelegramService(self._employees)

    async def list_messages(self) -> List[MessageOut]:
        return [MessageOut(**m) for m in self._repo.list()]

    async def send_message(self, data: MessageRequest) -> MessageOut:
        message_id = await self._telegram.send_message_to_user(
            data.user_id,
            data.message,
            parse_mode=data.parse_mode,
            photo_url=data.photo_url,
            require_ack=data.require_ack,
        )
        emp = next((e for e in self._employees.list_employees(archived=None)
                   if e.id == data.user_id), None)
        record = {
            "user_id": data.user_id,
            "name": emp.full_name if emp else data.user_id,
            "text": data.message,
            "photo": None,
            "status": "Отправлено",
            "accepted": False,
            "timestamp": datetime.utcnow().isoformat(),
            "message_id": message_id,
        }
        created = self._repo.create(record)
        return MessageOut(**created)

    async def accept_message(self, msg_id: str) -> Optional[MessageOut]:
        updated = self._repo.accept(msg_id)
        if updated:
            self._telegram.update_sent_message_status(
                updated["user_id"], updated["message_id"], "принято"
            )
            return MessageOut(**updated)
        return None

    @staticmethod
    def accept_by_details(user_id: str, message_id: int) -> None:
        MessageRepository().accept_by_details(user_id, message_id)

    @staticmethod
    def mark_message_as_accepted(msg_id: str) -> None:
        MessageRepository().accept(msg_id)
