import json
import re
import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from ...config import (
    ADMIN_CHAT_ID,
    USERS_FILE,
    MAX_ADVANCE_AMOUNT_PER_MONTH,
)
from ...services.users import load_users_map, save_users, add_user, update_user, delete_user
from ...services.advance_requests import load_advance_requests
from ...keyboards.reply_user import get_cabinet_menu, get_main_menu
from ...utils.logger import log


async def personal_cabinet(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    state = context.application.chat_data.get(chat_id, {}).get("conversation")
    log(f"[FSM] state before entry: {state}")
    user_id = str(update.effective_user.id)
    users = load_users_map()
    user = users.get(user_id)
    if not user:
        await update.message.reply_text(
            "❌ Ваши данные не найдены. Обратитесь к администратору.",
            reply_markup=get_main_menu(),
        )
        return
    name = user.get("name", "Не указано")
    await update.message.reply_text(
        f"👤 Добро пожаловать в личный кабинет, {name}!\nВыберите действие:",
        reply_markup=get_cabinet_menu(),
    )
    return ConversationHandler.END


async def view_user_info(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    users = load_users_map()
    user = users.get(user_id)
    if not user:
        await update.message.reply_text(
            "❌ Ваши данные не найдены.", reply_markup=get_main_menu()
        )
        return
    info_text = (
        f"📋 Ваши данные:\n"
        f"Имя: {user.get('name', 'Не указано')}\n"
        f"ФИО: {user.get('full_name', 'Не указано')}\n"
        f"Телефон: {user.get('phone', 'Не указано')}\n"
        f"Банк: {user.get('bank', 'Не указано')}\n"
        f"🎂 День рождения: {user.get('birthdate', 'Не указано')}"
    )
    await update.message.reply_text(info_text, reply_markup=get_cabinet_menu())


async def edit_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from ...keyboards.reply_user import get_edit_keyboard

    reply_markup = get_edit_keyboard()
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.message.reply_text(
            "✏️ Что вы хотите изменить?", reply_markup=reply_markup
        )
    elif update.message:
        await update.message.reply_text(
            "✏️ Что вы хотите изменить?", reply_markup=reply_markup
        )
    else:
        log("❌ [edit_user_info] Нет message и callback_query в update")


async def handle_edit_selection(update: Update,
                                context: ContextTypes.DEFAULT_TYPE) -> None:
    choice = update.message.text.strip()
    log(f"DEBUG [handle_edit_selection] Выбор: {choice}")
    if choice == "📱 Изменить телефон":
        context.user_data["edit_field"] = "phone"
        await update.message.reply_text(
            "Введите новый номер телефона (11 цифр, например, 89012345678):"
        )
    elif choice == "🏦 Изменить банк":
        context.user_data["edit_field"] = "bank"
        await update.message.reply_text(
            "Введите название банка (до 50 символов, только буквы, цифры, пробелы):"
        )
    else:
        await update.message.reply_text(
            "❌ Выберите корректный вариант.", reply_markup=get_cabinet_menu()
        )
        return
    context.user_data["awaiting_new_value"] = True
    log(
        f"DEBUG [handle_edit_selection] Установлены edit_field: {context.user_data.get('edit_field')}, awaiting_new_value: {context.user_data.get('awaiting_new_value')}"
    )


async def save_new_value(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("payout_request"):
        return
    if not context.user_data.get("awaiting_new_value"):
        return
    log(
        f"DEBUG [save_new_value] Текст: '{update.message.text if update.message else ''}', context.user_data: {context.user_data}"
    )
    new_value = update.message.text.strip()
    field = context.user_data.get("edit_field")
    if field == "phone":
        if not re.match(r"^\d{11}$", new_value):
            await update.message.reply_text(
                "❌ Номер телефона должен содержать ровно 11 цифр (например, 89012345678). Повторите ввод:"
            )
            return
    elif field == "bank":
        if len(new_value) > 50 or not re.match(
                r"^[a-zA-Zа-яА-Я0-9\s]+$", new_value):
            await update.message.reply_text(
                "❌ Название банка должно быть до 50 символов и содержать только буквы, цифры и пробелы. Повторите ввод:"
            )
            return
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{field}_{new_value}")],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel_edit")],
        ]
    )
    await update.message.reply_text(
        f"Новое значение для {field}: {new_value}\nПодтвердите изменение:",
        reply_markup=keyboard,
    )
    context.user_data["awaiting_new_value"] = False
    log(
        f"DEBUG [save_new_value] Запрос на подтверждение отправлен для {field}: {new_value}"
    )


async def handle_edit_confirmation(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "cancel_edit":
        await query.edit_message_text("❌ Изменение отменено.", reply_markup=None)
        context.user_data.pop("edit_field", None)
        context.user_data.pop("editing_info", None)
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text="Вы вернулись в личный кабинет.",
            reply_markup=get_cabinet_menu(),
        )
        return
    if data.startswith("confirm_"):
        _, field, new_value = data.split("_", 2)
        user_id = str(query.from_user.id)
        users = load_users_map()
        if user_id not in users:
            await query.edit_message_text("❌ Ваши данные не найдены.", reply_markup=None)
            context.user_data.clear()
            await context.bot.send_message(
                chat_id=user_id,
                text="Вы вернулись в главное меню.",
                reply_markup=get_main_menu(),
            )
            return
        users[user_id]["pending_change"] = {"field": field, "value": new_value}
        save_users(users)
        log(
            f"DEBUG [handle_edit_confirmation] Сохранено изменение для {user_id}: {field} → {new_value}"
        )
        admin_message = (
            f"🔔 Пользователь {users[user_id]['name']} хочет обновить данные:\n"
            f"Поле: {field}\n"
            f"Новое значение: {new_value}"
        )
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_change_{user_id}")],
                [InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_change_{user_id}")],
            ]
        )
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID, text=admin_message, reply_markup=keyboard
        )
        await query.edit_message_text(
            f"✅ Запрос на изменение {field} отправлен администратору на проверку.",
            reply_markup=None,
        )
        await context.bot.send_message(
            chat_id=user_id,
            text="Вы вернулись в личный кабинет.",
            reply_markup=get_cabinet_menu(),
        )
        context.user_data.pop("edit_field", None)
        context.user_data.pop("editing_info", None)


async def handle_admin_change_response(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("approve_change_"):
        user_id = data.split("_")[-1]
        users = load_users_map()
        if user_id not in users:
            await query.edit_message_text("❌ Пользователь не найден.")
            return
        pending_change = users[user_id].get("pending_change", {})
        field = pending_change.get("field")
        new_value = pending_change.get("value")
        if not field or not new_value:
            await query.edit_message_text("❌ Данные для изменения не найдены.")
            return
        old_value = users[user_id].get(field, "Не указано")
        users[user_id][field] = new_value
        del users[user_id]["pending_change"]
        save_users(users)
        log(
            f"✅ [admin_change] Пользователь {user_id} обновил {field}: {old_value} → {new_value}"
        )
        await query.edit_message_text(
            f"✅ Изменение {field} для {users[user_id]['name']} одобрено: {new_value}"
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ Ваш запрос на изменение {field} одобрен: {new_value}",
            reply_markup=get_cabinet_menu(),
        )
    elif data.startswith("reject_change_"):
        user_id = data.split("_")[-1]
        users = load_users_map()
        if user_id not in users:
            await query.edit_message_text("❌ Пользователь не найден.")
            return
        pending_change = users[user_id].get("pending_change", {})
        field = pending_change.get("field")
        new_value = pending_change.get("value")
        if "pending_change" in users[user_id]:
            del users[user_id]["pending_change"]
            save_users(users)
        log(
            f"❌ [admin_change] Изменение {field} для {user_id} отклонено: {new_value}")
        await query.edit_message_text(
            f"❌ Изменение {field} для {users[user_id]['name']} отклонено."
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=f"❌ Ваш запрос на изменение {field} отклонён администратором.",
            reply_markup=get_cabinet_menu(),
        )


async def view_request_history(update: Update,
                               context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    try:
        requests_list = load_advance_requests()
        if not isinstance(requests_list, list):
            log(
                f"❌ [view_request_history] Неверный формат данных в advance_requests: {requests_list}"
            )
            await update.message.reply_text(
                "❌ Ошибка загрузки истории запросов. Обратитесь к администратору.",
                reply_markup=get_cabinet_menu(),
            )
            return
    except Exception as e:
        log(
            f"❌ [view_request_history] Ошибка при загрузке запросов для user_id {user_id}: {e}"
        )
        await update.message.reply_text(
            "❌ Ошибка загрузки истории запросов. Обратитесь к администратору.",
            reply_markup=get_cabinet_menu(),
        )
        return
    user_requests = [r for r in requests_list if r["user_id"] == user_id][-5:]
    current_month = datetime.datetime.now().strftime("%Y-%m")
    user_advance_requests = [
        r
        for r in requests_list
        if r["user_id"] == user_id
        and r["status"] == "Одобрено"
        and r["timestamp"].startswith(current_month)
        and (r.get("payout_type") in ["Аванс", None] or "payout_type" not in r)
    ]
    total_advance_amount = sum(int(r.get("amount", 0))
                               for r in user_advance_requests)
    remaining_amount = MAX_ADVANCE_AMOUNT_PER_MONTH - total_advance_amount
    if not user_requests:
        await update.message.reply_text(
            f"📜 У вас пока нет запросов на выплату.\nАвансы за {current_month}: {total_advance_amount} ₽ из {MAX_ADVANCE_AMOUNT_PER_MONTH} ₽",
            reply_markup=get_cabinet_menu(),
        )
        return
    history_text = "📜 История ваших запросов (последние 5):\n\n"
    for req in reversed(user_requests):
        status_text = {
            "Ожидает": "⏳ Ожидает",
            "Одобрено": "✅ Одобрено",
            "Отклонено": "❌ Отклонено",
            "Отменено": "🚫 Отменено",
        }.get(req["status"], "Неизвестно")
        history_text += (
            f"Тип: {req.get('payout_type', 'Не указано')} ({req.get('method', 'Не указано')})\n"
            f"Сумма: {req.get('amount', 'Не указано')} ₽\n"
            f"Статус: {status_text}\n"
            f"Дата: {req.get('timestamp', 'Не указана')}\n\n"
        )
    history_text += f"Авансы за {current_month}: {total_advance_amount} ₽ из {MAX_ADVANCE_AMOUNT_PER_MONTH} ₽\nОстаток: {remaining_amount} ₽"
    await update.message.reply_text(
        history_text.strip(), reply_markup=get_cabinet_menu()
    )
    log(
        f"DEBUG [view_request_history] История запросов отправлена для user_id: {user_id}")
    context.user_data.clear()
