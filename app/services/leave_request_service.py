from datetime import datetime
from typing import List, Optional

from app.schemas.leave_request import LeaveRequest, LeaveRequestCreate
from app.data.leave_request_repository import LeaveRequestRepository
from app.core.enums import LEAVE_REQUEST_STATUSES

import logging
from pathlib import Path

logger = logging.getLogger("leave_request_actions")
if not logger.handlers:
    Path("logs").mkdir(exist_ok=True)
    handler = logging.FileHandler("logs/leave_request_actions.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class LeaveRequestService:
    def __init__(
        self,
        repo: Optional[LeaveRequestRepository] = None,
        telegram_service=None,
        push_service=None,
    ) -> None:
        self._repo = repo or LeaveRequestRepository()
        self._telegram = telegram_service
        self._push = push_service

    async def list_requests(self, employee_id: Optional[str] = None) -> List[LeaveRequest]:
        rows = self._repo.list(employee_id)
        return [LeaveRequest(**r) for r in rows]

    async def create_request(self, data: LeaveRequestCreate) -> LeaveRequest:
        if data.start_date > data.end_date:
            raise ValueError("start_date must be before end_date")
        request_dict = data.model_dump()
        request_dict["status"] = LEAVE_REQUEST_STATUSES[0]
        request_dict["created_at"] = datetime.now().isoformat()
        created = self._repo.create(request_dict)
        logger.info(
            f"🆕 Заявка на отсутствие '{created['type']}' от {created['start_date']} до "
            f"{created['end_date']} для {created['employee_id']}"
        )
        return LeaveRequest(**created)

    async def update_status(self, request_id: str, status: str) -> Optional[LeaveRequest]:
        updated = self._repo.update(request_id, {"status": status})
        if not updated:
            return None
        logger.info(f"✏️ Заявка {request_id} обновлена — статус: {status}")

        push_titles = {
            LEAVE_REQUEST_STATUSES[1]: "✅ Заявка на отсутствие одобрена",
            LEAVE_REQUEST_STATUSES[2]: "❌ Заявка на отсутствие отклонена",
        }
        push_title = push_titles.get(status)
        if push_title and self._push:
            try:
                body = f"{updated.get('type')}: {updated.get('start_date')} — {updated.get('end_date')}"
                await self._push.send(updated["employee_id"], push_title, body)
            except Exception as exc:
                logger.warning(f"Не удалось отправить push: {exc}")

        tg_messages = {
            LEAVE_REQUEST_STATUSES[1]: "✅ Ваша заявка на отсутствие одобрена",
            LEAVE_REQUEST_STATUSES[2]: "❌ Ваша заявка на отсутствие отклонена",
        }
        message = tg_messages.get(status)
        if message and self._telegram:
            try:
                await self._telegram.send_message_to_user(
                    updated["employee_id"],
                    f"{message}\n{updated.get('type')}: {updated.get('start_date')} — {updated.get('end_date')}",
                )
            except Exception as exc:
                logger.warning(f"Не удалось уведомить пользователя: {exc}")
        return LeaveRequest(**updated)

    async def delete_request(self, request_id: str) -> None:
        self._repo.delete(request_id)
        logger.info(f"🗑 Удалена заявка {request_id}")

    def get_request_employee(self, request_id: str) -> Optional[str]:
        row = self._repo.get(request_id)
        if not row:
            return None
        employee_id = row.get("employee_id")
        return str(employee_id) if employee_id is not None else None
