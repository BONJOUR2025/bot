from datetime import datetime
from typing import List, Optional

from app.schemas.employee_message import EmployeeMessage, EmployeeMessageCreate
from app.data.employee_message_repository import EmployeeMessageRepository

import logging
from pathlib import Path

logger = logging.getLogger("employee_message_actions")
if not logger.handlers:
    Path("logs").mkdir(exist_ok=True)
    handler = logging.FileHandler("logs/employee_message_actions.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class EmployeeMessageService:
    def __init__(
        self,
        repo: Optional[EmployeeMessageRepository] = None,
        telegram_service=None,
        push_service=None,
    ) -> None:
        self._repo = repo or EmployeeMessageRepository()
        self._telegram = telegram_service
        self._push = push_service

    async def list_messages(self, employee_id: Optional[str] = None) -> List[EmployeeMessage]:
        rows = self._repo.list(employee_id)
        return [EmployeeMessage(**r) for r in rows]

    async def create_message(self, data: EmployeeMessageCreate) -> EmployeeMessage:
        record = data.model_dump()
        record["status"] = "new"
        record["created_at"] = datetime.now().isoformat()
        created = self._repo.create(record)
        logger.info(f"🆕 Сообщение от {created['employee_id']} ({created['name']})")
        if self._telegram:
            try:
                await self._telegram.send_employee_message_to_admin(
                    created["name"], created["message"]
                )
            except Exception as exc:
                logger.warning(f"Не удалось уведомить администратора: {exc}")
        return EmployeeMessage(**created)

    async def mark_read(self, message_id: str) -> Optional[EmployeeMessage]:
        updated = self._repo.update(message_id, {"status": "read"})
        return EmployeeMessage(**updated) if updated else None

    async def reply(self, message_id: str, reply: str) -> Optional[EmployeeMessage]:
        updated = self._repo.update(
            message_id,
            {"status": "replied", "reply": reply, "replied_at": datetime.now().isoformat()},
        )
        if not updated:
            return None
        logger.info(f"✏️ Ответ на сообщение {message_id}")
        if self._telegram:
            try:
                await self._telegram.send_message_to_user(
                    updated["employee_id"],
                    f"💬 Ответ администратора:\n{reply}",
                )
            except Exception as exc:
                logger.warning(f"Не удалось уведомить сотрудника: {exc}")
        if self._push:
            try:
                await self._push.send(
                    updated["employee_id"], "💬 Ответ администратора", reply
                )
            except Exception as exc:
                logger.warning(f"Не удалось отправить push: {exc}")
        return EmployeeMessage(**updated)

    def get_message_employee(self, message_id: str) -> Optional[str]:
        row = self._repo.get(message_id)
        if not row:
            return None
        employee_id = row.get("employee_id")
        return str(employee_id) if employee_id is not None else None
