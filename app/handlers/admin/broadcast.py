"""Функции для рассылки сообщений администраторами."""

import asyncio
from telegram import (
    Message,
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import Application, ContextTypes, ConversationHandler
from telegram.error import BadRequest
import requests

from ...services.advance_requests import API_URL

from ...config import ADMIN_ID
from ...services.users import load_users
from ...utils.logger import log
from ...constants import UserStates
from ...keyboards.reply_admin import get_home_button, get_admin_menu


async def send_message(
    app: Application, user_id: int, message: Message
) -> None:
    """Отправляет сообщение конкретному пользователю."""
    log(
        f"[Telegram] broadcasting message to {user_id} — text: '{(message.text or message.caption or '')[:50]}'"
    )
    try:
        if message.text:
            requests.post(
                f"{API_URL}/telegram/send_message",
                json={"user_id": str(user_id), "message": message.text},
            )
        elif message.photo:
            await app.bot.send_photo(
                chat_id=user_id,
                photo=message.photo[-1].file_id,
                caption=message.caption or "",
            )
        log(f"✅ [send_message] Сообщение отправлено пользователю {user_id}")
    except BadRequest as e:
        log(f"❌ Failed to send message to chat {user_id} — {e}")
        raise
    except Exception as e:
        log(f"❌ [send_message] Ошибка отправки пользователю {user_id}: {e}")


async def send_broadcast_message(
    app: Application, message: Message, user_list: list[int]
) -> None:
    """Отправляет сообщение всем пользователям из списка."""
    for i, user_id in enumerate(user_list, start=1):
        await send_message(app, user_id, message)
        if i % 15 == 0:
            await asyncio.sleep(1)


async def handle_broadcast_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Запускает процесс рассылки."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав для рассылки.")
        return

    if update.message.text != "📢 Рассылка":
        return

    log(
        f"📢 [handle_broadcast_start] Администратор {user_id} начал процесс рассылки"
    )
    await update.message.reply_text(
        "Введите текст сообщения для рассылки всем пользователям:",
        reply_markup=get_home_button(),
    )
    context.user_data["broadcast_in_progress"] = True
    return UserStates.BROADCAST_MESSAGE


async def handle_broadcast_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Принимает текст рассылки и запрашивает подтверждение."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID or not context.user_data.get(
        "broadcast_in_progress"
    ):
        return ConversationHandler.END

    message_text = update.message.text.strip()
    if message_text == "🏠 Домой":
        context.user_data.pop("broadcast_in_progress", None)
        await update.message.reply_text(
            "🏠 Рассылка отменена.", reply_markup=get_admin_menu()
        )
        return ConversationHandler.END

    log(
        f"📢 [handle_broadcast_message] Текст рассылки от {user_id}: {message_text}"
    )
    context.user_data["broadcast_text"] = message_text

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Отправить", callback_data="broadcast_confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    "✏️ Изменить", callback_data="broadcast_edit"
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 Отмена", callback_data="broadcast_cancel"
                )
            ],
        ]
    )
    await update.message.reply_text(
        f"Подтвердите текст рассылки:\n\n{message_text}",
        reply_markup=keyboard,
    )
    return UserStates.BROADCAST_CONFIRM


async def handle_broadcast_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Обрабатывает подтверждение или отмену рассылки."""
    query = update.callback_query
    await query.answer()

    if query.data == "broadcast_confirm":
        return await handle_broadcast_send(update, context)
    if query.data == "broadcast_edit":
        log(
            f"[Telegram] editing message {query.message.message_id} in {query.message.chat.id}"
        )
        try:
            await query.edit_message_text("Введите новый текст для рассылки:")
        except BadRequest as e:
            log(
                f"❌ Failed to edit message {query.message.message_id} in chat {query.message.chat.id} — {e}"
            )
            raise
        return UserStates.BROADCAST_MESSAGE

    context.user_data.pop("broadcast_in_progress", None)
    context.user_data.pop("broadcast_text", None)
    log(
        f"[Telegram] editing message {query.message.message_id} in {query.message.chat.id}"
    )
    try:
        await query.edit_message_text(
            "🏠 Рассылка отменена.", reply_markup=get_admin_menu()
        )
    except BadRequest as e:
        log(
            f"❌ Failed to edit message {query.message.message_id} in chat {query.message.chat.id} — {e}"
        )
        raise
    return ConversationHandler.END


async def handle_broadcast_send(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Отправляет подтверждённое сообщение всем пользователям."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID or not context.user_data.get(
        "broadcast_in_progress"
    ):
        return ConversationHandler.END

    message_text = context.user_data.get("broadcast_text")
    if not message_text:
        await update.message.reply_text(
            "❌ Текст рассылки не найден.", reply_markup=get_admin_menu()
        )
        return ConversationHandler.END

    log(
        f"📢 [handle_broadcast_send] Отправка рассылки от {user_id}: {message_text}"
    )

    users = load_users()
    user_ids = [int(uid) for uid in users.keys()]

    message = update.message
    message.text = message_text

    await send_broadcast_message(context.application, message, user_ids)

    context.user_data.pop("broadcast_in_progress", None)
    context.user_data.pop("broadcast_text", None)
    await update.message.reply_text(
        f"✅ Рассылка успешно отправлена {len(user_ids)} пользователям!",
        reply_markup=get_admin_menu(),
    )
    log(
        f"✅ [handle_broadcast_send] Рассылка завершена для {
            len(user_ids)} пользователей")
    return ConversationHandler.END
