from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Sequence, List, Dict
from datetime import datetime

from telegram import Bot
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

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
        Path("logs").mkdir(exist_ok=True)
        self.msg_log = Path("logs/sent_messages.json")
        if not self.msg_log.exists():
            self.msg_log.write_text("[]", encoding="utf-8")

    def _load_log(self) -> List[Dict]:
        try:
            return json.loads(self.msg_log.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_log(self, data: List[Dict]) -> None:
        self.msg_log.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def update_sent_message_status(
        cls, user_id: str, message_id: int, status: str
    ) -> None:
        log_file = Path("logs/sent_messages.json")
        if not log_file.exists():
            return
        try:
            data = json.loads(log_file.read_text(encoding="utf-8"))
        except Exception:
            return
        for item in data:
            if (
                str(item.get("user_id")) == str(user_id)
                and item.get("message_id") == message_id
            ):
                item["status"] = status
                break
        log_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

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

    async def send_message_to_user(
        self,
        user_id: str,
        message: str,
        parse_mode: str = "HTML",
        photo_url: Optional[str] = None,
        require_ack: bool = False,
    ) -> int:
        reply_markup = None
        if require_ack:
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("✅ Принято", callback_data=f"ack_{user_id}")]]
            )
        if photo_url:
            result = await self.bot.send_photo(
                chat_id=user_id,
                photo=photo_url,
                caption=message,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
        else:
            result = await self.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
        log_entry = {
            "user_id": str(user_id),
            "message": message,
            "status": "отправлено",
            "message_id": result.message_id,
            "timestamp": datetime.utcnow().isoformat(),
            "photo_url": photo_url,
            "requires_ack": require_ack,
        }
        data = self._load_log()
        data.append(log_entry)
        self._save_log(data)
        return result.message_id
