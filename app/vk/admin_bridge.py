"""Notify the Telegram admin from the VK process.

The VK bot and Telegram bot are separate processes — this module doesn't
talk to the Telegram bot's running Application, it just makes its own
Telegram Bot API calls (TelegramService creates its own httpx-backed Bot
instance when not given one). The admin's approve/reject tap is still a
Telegram callback_query, delivered to whichever process is polling
(app.main) — so it lands on the existing, unmodified Telegram handlers in
app/handlers/user/cabinet.py (handle_admin_change_response) without VK
needing to know or care that Telegram is the one handling the button press.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.data.employee_repository import EmployeeRepository
from app.services.telegram_service import TelegramService
from app.utils.logger import log


async def notify_admin_profile_change(employee_id: str, employee_name: str, field: str, new_value: str) -> None:
    service = TelegramService(EmployeeRepository())
    from app.services import notification_routing

    chat_ids = notification_routing.recipients("employee_changes")
    if service.bot is None or not chat_ids:
        log("⚠️ [vk] Telegram-бот не настроен или уведомления «Изменение данных сотрудников» выключены")
        return
    text = (
        f"🔴 РЕШЕНИЕ · Изменение данных сотрудника (VK)\n"
        f"{employee_name} хочет обновить данные:\n"
        f"Поле: {field}\n"
        f"Новое значение: {new_value}"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_change_{employee_id}")],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_change_{employee_id}")],
    ])
    try:
        for chat_id in chat_ids:
            await service.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    except Exception as exc:
        log(f"❌ [vk] Не удалось уведомить админа о смене данных: {exc}")
