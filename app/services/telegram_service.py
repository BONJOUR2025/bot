from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Sequence, List, Dict, Any
from datetime import datetime

from telegram import Bot
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from app.utils.logger import log
from app.utils import is_valid_user_id

from app.config import TOKEN, ADMIN_CHAT_ID
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
        if not ADMIN_CHAT_ID:
            log("⚠️ ADMIN_CHAT_ID not configured")

    def _load_log(self) -> List[Dict]:
        """Return log records sorted by timestamp descending."""
        try:
            data = json.loads(self.msg_log.read_text(encoding="utf-8"))
        except Exception:
            return []
        return sorted(
            data,
            key=lambda x: x.get(
                "timestamp",
                ""),
            reverse=True)[
            :50]

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
            self,
            message: str,
            parse_mode: str = "HTML",
            photo_url: Optional[str] = None) -> dict:
        employees = self.repo.list_employees()
        success = 0
        for emp in employees:
            if not is_valid_user_id(emp.id):
                log(f"⚠️ Skipping message — invalid or fake user_id: {emp.id}")
                continue
            log(
                f"[Telegram] Broadcasting to {emp.id} — text: '{message[:50]}', photo: {bool(photo_url)}"
            )
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
                        chat_id=emp.id,
                        text=message,
                        parse_mode=parse_mode,
                    )
                success += 1
                logger.info(f"Sent to {emp.id}")
            except BadRequest as exc:
                log(f"❌ Failed to send broadcast to chat {emp.id} — {exc}")
                raise
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
        if not is_valid_user_id(user_id):
            log(f"⚠️ Skipping message — invalid or fake user_id: {user_id}")
            return 0
        reply_markup = None
        if require_ack:
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("✅ Принято", callback_data=f"ack_{user_id}")]]
            )
        log(
            f"[Telegram] Sending personal message to {user_id} — text: '{message[:50]}'"
        )
        try:
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
        except BadRequest as exc:
            log(f"❌ Failed to send message to chat {user_id} — {exc}")
            raise
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

    async def send_payout_request_to_admin(self, payout: Dict[str, Any]) -> None:
        """Notify the admin chat about a payout request."""
        text = (
            "📥 Новый запрос на выплату:\n\n"
            f"👤 {payout['name']}\n"
            f"📱 {payout['phone']}\n"
            f"🏦 {payout['bank']}\n"
            f"💰 Сумма: {payout['amount']} ₽\n"
            f"💳 Метод: {payout['method']}\n"
            f"📂 Тип: {payout['payout_type']}"
        )
        markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Разрешить", callback_data=f"allow_payout_{payout['user_id']}")],
                [InlineKeyboardButton("❌ Отклонить", callback_data=f"deny_payout_{payout['user_id']}")],
            ]
        )
        if not ADMIN_CHAT_ID:
            log("⚠️ ADMIN_CHAT_ID not configured; cannot notify admin")
            return
        log(
            f"[Telegram] Sending payout approval request to {ADMIN_CHAT_ID} — text: '{text[:50]}'"
        )
        try:
            await self.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=text,
                reply_markup=markup,
            )
        except BadRequest as exc:
            log(f"❌ Failed to send message to chat {ADMIN_CHAT_ID} — {exc}")
            raise
