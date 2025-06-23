# Handler functions for payout approval and rejection.
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import BadRequest

from ...constants import UserStates
from ...config import (
    ADMIN_ID,
    ADMIN_CHAT_ID,
    CARD_DISPATCH_CHAT_ID,
)
from ...services.users import load_users
from ...keyboards.reply_admin import get_admin_menu
from ...services.advance_requests import (
    load_advance_requests,
    save_advance_requests,
    update_request_status,
)
from ...utils.logger import log
from ...utils import is_valid_user_id

PENDING_STATUSES = {"Ожидает", "В ожидании"}


async def allow_payout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.data.split("_")[-1]
    log(f"✅ [allow_payout] Одобрение выплаты для user_id: {user_id}")

    payout_requests = load_advance_requests()
    request_to_approve = next(
        (
            r
            for r in payout_requests
            if r["user_id"] == user_id and r.get("status") in PENDING_STATUSES
        ),
        None,
    )
    if not request_to_approve:
        await query.edit_message_text("❌ Нет активного запроса для одобрения.")
        return

    try:
        update_request_status(user_id, "approved")
        log(
            f"✅ Статус выплаты для user_id {user_id} обновлён на Одобрено"
        )
    except Exception as e:
        log(f"❌ Ошибка обновления статуса выплаты: {e}")

    payout_type = request_to_approve.get("payout_type") or "Не указано"
    user_message = (
        f"✅ Ваш запрос на выплату одобрен!\n"
        f"Тип: {payout_type}\n"
        f"Сумма: {request_to_approve['amount']} ₽\n"
        f"Метод: {request_to_approve['method']}"
    )
    log(
        f"[Telegram] sending approval notice to {user_id} — text: '{user_message[:50]}'"
    )
    if is_valid_user_id(user_id):
        try:
            await context.bot.send_message(chat_id=user_id, text=user_message)
        except BadRequest as e:
            log(f"❌ Failed to send message to chat {user_id} — {e}")
            raise
    else:
        log(f"⚠️ Skipping message — invalid or fake user_id: {user_id}")

    current_text = query.message.text
    updated_text = f"{current_text}\n\n✅ Разрешено"
    log(
        f"[Telegram] editing message {query.message.message_id} in {query.message.chat.id}"
    )
    try:
        await query.edit_message_text(text=updated_text)
    except BadRequest as e:
        log(
            f"❌ Failed to edit message {query.message.message_id} in chat {query.message.chat.id} — {e}"
        )
        raise

    if request_to_approve["method"] == "💳 На карту":
        cashier_text = (
            f"📤 Запрос на перевод:\n\n"
            f"👤 {request_to_approve['name']}\n"
            f"📱 {request_to_approve['phone']}\n"
            f"🏦 {request_to_approve['bank']}\n"
            f"💰 {request_to_approve['amount']} ₽\n"
            f"📂 {payout_type}"
        )
        cashier_buttons = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📤 Отправлено", callback_data=f"mark_sent_{user_id}")]]
        )
        log(
            f"[Telegram] sending cashier notice to {CARD_DISPATCH_CHAT_ID} — text: '{cashier_text[:50]}'"
        )
        try:
            await context.bot.send_message(
                chat_id=CARD_DISPATCH_CHAT_ID,
                text=cashier_text,
                reply_markup=cashier_buttons,
            )
            log(f"📨 [allow_payout] Сообщение кассиру отправлено для user_id: {user_id}")
        except BadRequest as e:
            log(f"❌ Failed to send message to chat {CARD_DISPATCH_CHAT_ID} — {e}")
            raise
        except Exception as e:
            log(f"❌ [allow_payout] Ошибка отправки кассиру: {e}")


async def deny_payout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.data.split("_")[-1]
    log(f"❌ [deny_payout] Отклонение выплаты для user_id: {user_id}")

    payout_requests = load_advance_requests()
    request_to_deny = next(
        (
            r
            for r in payout_requests
            if r["user_id"] == user_id and r.get("status") in PENDING_STATUSES
        ),
        None,
    )
    if not request_to_deny:
        await query.edit_message_text("❌ Нет активного запроса для отклонения.")
        return

    try:
        update_request_status(user_id, "rejected")
        log(
            f"✅ Статус выплаты для user_id {user_id} обновлён на Отклонено"
        )
    except Exception as e:
        log(f"❌ Ошибка обновления статуса выплаты: {e}")

    payout_type = request_to_deny.get("payout_type") or "Не указано"
    user_message = (
        f"❌ Ваш запрос на выплату отклонён.\n"
        f"Тип: {payout_type}\n"
        f"Сумма: {request_to_deny['amount']} ₽\n"
        f"Метод: {request_to_deny['method']}"
    )
    log(
        f"[Telegram] sending denial notice to {user_id} — text: '{user_message[:50]}'"
    )
    if is_valid_user_id(user_id):
        try:
            await context.bot.send_message(chat_id=user_id, text=user_message)
        except BadRequest as e:
            log(f"❌ Failed to send message to chat {user_id} — {e}")
            raise
    else:
        log(f"⚠️ Skipping message — invalid or fake user_id: {user_id}")

    current_text = query.message.text
    updated_text = f"{current_text}\n\n❌ Отказано"
    log(
        f"[Telegram] editing message {query.message.message_id} in {query.message.chat.id}"
    )
    try:
        await query.edit_message_text(text=updated_text, reply_markup=None)
    except BadRequest as e:
        log(
            f"❌ Failed to edit message {query.message.message_id} in chat {query.message.chat.id} — {e}"
        )
        raise


async def reset_payout_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return

    payout_requests = load_advance_requests()
    if not payout_requests:
        await update.message.reply_text(
            "📭 Нет запросов в файле для сброса.",
            reply_markup=get_admin_menu(),
        )
        return

    pending_requests = [
        req
        for req in payout_requests
        if req.get("status") in PENDING_STATUSES
    ]
    reset_details = []

    if pending_requests:
        for req in pending_requests:
            req["status"] = "Отменено"
            update_request_status(req["user_id"], "cancelled")
            reset_details.append(
                f"👤 {req['name']} (ID: {req['user_id']})\n"
                f"Сумма: {req['amount']} ₽\n"
                f"Метод: {req['method']}\n"
                f"Тип: {req.get('payout_type', 'Не указано')}"
            )
        save_advance_requests(payout_requests)
        log(
            f"✅ [reset_payout_request] Сброшено {len(pending_requests)} запросов из файла: {reset_details}"
        )
    else:
        log("⚠️ [reset_payout_request] Нет активных запросов в файле.")

    users = load_users()
    reset_users = []
    persistence = getattr(context.application, "persistence", None)
    for uid in users.keys():
        user_data = persistence.get_user_data().get(int(uid), {}) if persistence else {}
        if user_data and "payout_in_progress" in user_data:
            reset_users.append(f"👤 {users[uid].get('name', 'Неизвестно')} (ID: {uid})")
            user_data.pop("payout_in_progress", None)
            user_data.pop("payout_data", None)
            if persistence:
                persistence.update_user_data(int(uid), user_data)

    message_lines = []
    if pending_requests:
        message_lines.append(f"✅ Сброшено {len(pending_requests)} запросов из файла:")
        message_lines.extend([f"Запрос #{i+1}:\n{detail}" for i, detail in enumerate(reset_details)])
    else:
        message_lines.append("📭 Нет активных запросов в файле.")

    if reset_users:
        message_lines.append(f"\n✅ Очищено {len(reset_users)} зависших состояний:")
        message_lines.extend([f"Пользователь #{i+1}: {user}" for i, user in enumerate(reset_users)])
    else:
        message_lines.append("\n📭 Нет зависших состояний у пользователей.")

    reset_message = "\n\n".join(message_lines)
    await update.message.reply_text(reset_message, reply_markup=get_admin_menu())
    log(f"✅ [reset_payout_request] Завершён сброс: {reset_message}")


async def mark_sent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.data.split("_")[-1]
    current_text = query.message.text
    updated_text = f"{current_text}\n\n📤 Отправлено"
    log(
        f"[Telegram] editing message {query.message.message_id} in {query.message.chat.id}"
    )
    try:
        await query.edit_message_text(updated_text)
    except BadRequest as e:
        log(
            f"❌ Failed to edit message {query.message.message_id} in chat {query.message.chat.id} — {e}"
        )
        raise
