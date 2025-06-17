from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Sequence

from telegram import Bot

from app.config import TOKEN
from app.data.employee_repository import EmployeeRepository

logger = logging.getLogger("broadcast")
if not logger.handlers:
    Path("logs").mkdir(exist_ok=True)
    fh = logging.FileHandler("logs/broadcast.log", encoding="utf-8")
    formatter = logging.Formatter("[%(asctime)s] %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.setLevel(logging.INFO)


class TelegramService:
    def __init__(self, repo: EmployeeRepository) -> None:
        self.repo = repo
        self.bot = Bot(token=TOKEN)

    async def broadcast_message_to_all(
        self, message: str, parse_mode: str = "HTML", photo_url: Optional[str] = None
    ) -> dict:
        employees = self.repo.list_employees()
        success = 0
        for emp in employees:
            try:
                if photo_url:
                    await self.bot.send_photo(
                        chat_id=emp.id,
                        photo=photo_url,
                        caption=message,
                        parse_mode=parse_mode,
                    )
                else:
                    await self.bot.send_message(
                        chat_id=emp.id, text=message, parse_mode=parse_mode
                    )
                success += 1
                logger.info(f"Sent to {emp.id}")
            except Exception as exc:
                logger.warning(f"Failed for {emp.id}: {exc}")
        return {"success": True, "sent": success, "total": len(employees)}
