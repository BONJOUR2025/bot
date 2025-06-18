from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from ...config import (
    ADMIN_CHAT_ID,
    MAX_ADVANCE_AMOUNT_PER_MONTH,
    CARD_DISPATCH_CHAT_ID,
)
from ...services.users import load_users, save_users
from ...services.advance_requests import (
    log_new_request,
    check_pending_request,
    load_advance_requests,
)
from ...keyboards.reply_user import get_main_menu
from ...utils.logger import log

from ...constants import PayoutStates


async def request_payout_user(update: Update,
                              context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    log(f"DEBUG [request_payout_user] Запрос выплаты от user_id: {user_id}")
    users = load_users()
    if user_id not in users:
        if update.message:
            await update.message.reply_text(
                "❌ Вы не зарегистрированы.", reply_markup=get_main_menu()
            )
        return ConversationHandler.END
    if check_pending_request(user_id):
        if update.message:
            await update.message.reply_text(
                "❌ У вас уже есть необработанный запрос.",
                reply_markup=get_main_menu(),
            )
        log(
            f"DEBUG [request_payout_user] Обнаружен pending-запрос для {user_id}")
        return ConversationHandler.END
    requests_list = load_advance_requests()
    total_advance_amount = sum(
        req["amount"]
        for req in requests_list
        if req["user_id"] == user_id and req["status"] == "Одобрено"
    )
    log(
        f"DEBUG [request_payout_user] total_advance_amount: {total_advance_amount}")
    if total_advance_amount >= MAX_ADVANCE_AMOUNT_PER_MONTH:
        if update.message:
            await update.message.reply_text(
                f"❌ Вы превысили лимит аванса ({MAX_ADVANCE_AMOUNT_PER_MONTH} ₽).",
                reply_markup=get_main_menu(),
            )
        log(f"DEBUG [request_payout_user] Лимит аванса превышен для {user_id}")
        return ConversationHandler.END
    keyboard = [["Аванс", "Зарплата"], ["🏠 Домой"]]
    if update.message:
        await update.message.reply_text(
            "Выберите тип выплаты:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard, resize_keyboard=True, one_time_keyboard=True
            ),
        )
    log(
        "DEBUG [request_payout_user] Клавиатура отправлена, переход в состояние PayoutStates.SELECT_TYPE"
    )
    return PayoutStates.SELECT_TYPE


async def handle_payout_type_user(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE):
    payout_type = update.message.text
    user_id = str(update.effective_user.id)
    log(f"DEBUG [handle_payout_type_user] Выбран тип выплаты: {payout_type}")
    if "payout_data" not in context.user_data:
        context.user_data["payout_data"] = {}
    context.user_data["payout_data"]["payout_type"] = payout_type
    context.user_data["awaiting_amount"] = True
    await update.message.reply_text(
        "💸 Введите сумму выплаты цифрами (например, 10000):"
    )
    return PayoutStates.ENTER_AMOUNT


async def handle_payout_amount_user(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    log(
        f"DEBUG [handle_payout_amount_user] Текст: '{text}', awaiting_amount: {
            context.user_data.get('awaiting_amount')}")
    if not text.isdigit():
        await update.message.reply_text("❌ Введите корректную сумму цифрами.")
        return PayoutStates.ENTER_AMOUNT
    amount = int(text)
    payout_data = context.user_data.get("payout_data", {})
    payout_type = payout_data.get("payout_type")
    if not payout_type:
        await update.message.reply_text(
            "❌ Тип выплаты не определён. Начните сначала."
        )
        return ConversationHandler.END
    context.user_data["payout_data"] = {
        "amount": amount,
        "payout_type": payout_type,
        "method": payout_data.get("method"),
        "awaiting_amount": False,
    }
    log(
        f"DEBUG [handle_payout_amount_user] Сумма {amount} принята для user_id: {user_id}, ожидается выбор метода"
    )
    keyboard = [["💵 Из кассы", "💳 На карту"], ["🏠 Домой"]]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=False
    )
    await update.message.reply_text(
        "💳 Выберите способ выплаты:", reply_markup=reply_markup
    )
    return PayoutStates.SELECT_METHOD


async def payout_method_user(update: Update,
                             context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    method = update.message.text
    payout_data = context.user_data.get("payout_data", {})
    payout_data["method"] = method
    context.user_data["payout_data"] = payout_data
    log(
        f"DEBUG [payout_method_user] Выбран метод: {method} для user_id: {user_id}")
    if method == "💳 На карту":
        users = load_users()
        user_info = users.get(str(user_id), {})
        name = user_info.get("name", "—")
        phone = user_info.get("phone", "—")
        bank = user_info.get("bank", "—")
        card_text = (
            f"🧾 Текущие реквизиты:\n\n👤 Имя: {name}\n📱 Телефон: {phone}\n🏦 Банк: {bank}\n\nПодтвердите, чтобы отправить запрос."
        )
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_card")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel_card")],
            ]
        )
        await update.message.reply_text(card_text, reply_markup=keyboard)
        return PayoutStates.CONFIRM_CARD
    else:
        return await confirm_payout_user(update, context)


async def handle_card_confirmation(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    log(
        f"DEBUG [handle_card_confirmation] Начало обработки для user_id: {user_id}")
    payout_data = context.user_data.get("payout_data", {})
    method = payout_data.get("method")
    amount = payout_data.get("amount")
    payout_type = payout_data.get("payout_type")
    if not all([amount, method, payout_type]):
        log(
            f"❌ [handle_card_confirmation] Недостаточно данных: {
                amount=}, {
                method=}, {
                payout_type=}")
        await query.edit_message_text(
            "❌ Невозможно сформировать запрос: недостаточно данных."
        )
        return ConversationHandler.END
    card_info = context.user_data.get("card_temp")
    if not card_info:
        users = load_users()
        user_info = users.get(user_id, {})
        card_info = {
            "name": user_info.get("name", "—"),
            "phone": user_info.get("phone", "—"),
            "bank": user_info.get("bank", "—"),
        }
    name = card_info.get("name")
    phone = card_info.get("phone")
    bank = card_info.get("bank")
    users = load_users()
    if user_id in users:
        users[user_id]["name"] = name
        users[user_id]["phone"] = phone
        users[user_id]["bank"] = bank
        save_users(users)
    try:
        log(f"DEBUG [handle_card_confirmation] Логируем запрос для {user_id}")
        log_new_request(
            user_id,
            name,
            phone,
            bank,
            amount,
            method,
            payout_type)
    except Exception as e:
        log(f"❌ [handle_card_confirmation] Ошибка записи запроса: {e}")
        await query.edit_message_text(
            "❌ Не удалось сохранить запрос. Попробуйте позже."
        )
        return ConversationHandler.END
    await query.edit_message_text(
        "✅ Ваш запрос отправлен администратору.\n" "Обратите внимание! Рассмотрение запроса может занять до 2-х рабочих дней",
    )
    # отправляем отдельным сообщением главное меню, т.к. edit_message_text
    # поддерживает только inline-клавиатуры
    await query.message.reply_text(
        "🏠 Главное меню",
        reply_markup=get_main_menu(),
    )
    admin_text = (
        f"📥 Новый запрос на выплату:\n\n"
        f"👤 {name}\n"
        f"📱 {phone}\n"
        f"🏦 {bank}\n"
        f"💰 Сумма: {amount} ₽\n"
        f"💳 Метод: {method}\n"
        f"📂 Тип: {payout_type}"
    )
    admin_buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Разрешить", callback_data=f"allow_payout_{user_id}")],
            [InlineKeyboardButton("❌ Отклонить", callback_data=f"deny_payout_{user_id}")],
        ]
    )
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID, text=admin_text, reply_markup=admin_buttons
        )
    except Exception as e:
        log(f"❌ [handle_card_confirmation] Ошибка отправки сообщения: {e}")
        await query.edit_message_text(
            "❌ Ошибка при отправке запроса. Попробуйте позже."
        )
        return ConversationHandler.END
    if query.data == "cancel_card":
        log(f"DEBUG [handle_card_confirmation] Запрос отменён для {user_id}")
        await query.edit_message_text("❌ Выплата отменена.")
        context.user_data.pop("payout_data", None)
        return ConversationHandler.END
    log(f"DEBUG [handle_card_confirmation] Завершение обработки для {user_id}")
    context.user_data.pop("payout_data", None)
    return ConversationHandler.END


async def confirm_payout_user(update: Update,
                              context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        query = update.callback_query
        user_id = str(query.from_user.id)
        message = query.message
        await query.answer()
    else:
        user_id = str(update.effective_user.id)
        message = update.message
    log(f"DEBUG [confirm_payout_user] Начало обработки для user_id: {user_id}")
    payout_data = context.user_data.get("payout_data", {})
    amount = payout_data.get("amount")
    payout_type = payout_data.get("payout_type")
    payout_method = payout_data.get("method")
    if not all([amount, payout_type, payout_method]):
        log(
            f"❌ [confirm_payout_user] Недостаточно данных: {
                amount=}, {
                payout_type=}, {
                payout_method=}")
        await message.reply_text(
            "❌ Запрос неполный, начните сначала.",
            reply_markup=get_main_menu(),
        )
        context.user_data.clear()
        return ConversationHandler.END
    users = load_users()
    user = users.get(user_id)
    if not user:
        log(f"❌ [confirm_payout_user] Пользователь {user_id} не найден")
        await message.reply_text(
            "❌ Информация о пользователе не найдена.",
            reply_markup=get_main_menu(),
        )
        context.user_data.clear()
        return ConversationHandler.END
    name = user.get("name")
    phone = user.get("phone", "Не указан")
    bank = user.get("bank")
    admin_notification = (
        f"Новый запрос на выплату:\n"
        f"Тип выплаты: {payout_type}\n"
        f"Сумма: {amount} ₽\n"
        f"Способ выплаты: {'Переводом на карту' if payout_method == '💳 На карту' else payout_method}\n\n"
        f"Пользователь: {name}\n"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Разрешить", callback_data=f"allow_payout_{user_id}")],
            [InlineKeyboardButton("❌ Запретить", callback_data=f"deny_payout_{user_id}")],
        ]
    )
    try:
        log(f"DEBUG [confirm_payout_user] Логируем запрос для {user_id}")
        log_new_request(
            user_id, name, phone, bank, amount, payout_method, payout_type
        )
    except Exception as e:
        log(f"❌ [confirm_payout_user] Ошибка записи запроса: {e}")
        await message.reply_text(
            "❌ Не удалось сохранить запрос. Попробуйте позже."
        )
        return ConversationHandler.END
    try:
        log(f"DEBUG [confirm_payout_user] Отправляем сообщение администратору")
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_notification,
            reply_markup=keyboard,
        )
    except Exception as e:
        log(
            f"❌ [confirm_payout_user] Ошибка отправки сообщения администратору: {e}")
        await message.reply_text(
            "❌ Ошибка при отправке запроса администратору. Попробуйте позже."
        )
        return ConversationHandler.END
    log(
        f"DEBUG [confirm_payout_user] Отправляем подтверждение пользователю {user_id}")
    await message.reply_text(
        f"✅ Ваш запрос на ({amount} ₽, {payout_method}) отправлен.",
        reply_markup=get_main_menu(),
    )
    log(
        f"✅ [confirm_payout_user] Пользователь {user_id} успешно отправил запрос на выплату {amount} ₽"
    )
    context.user_data.pop("payout_data", None)
    return ConversationHandler.END


async def change_payout_amount(update: Update,
                               context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "💸 Введите новую сумму выплаты:"
    )
    context.user_data["payout_data"].pop("amount", None)
    context.user_data["awaiting_amount"] = True
    return PayoutStates.ENTER_AMOUNT


async def change_payout_type(update: Update,
                             context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    keyboard = ReplyKeyboardMarkup(
        [["Аванс", "Зарплата"], ["🏠 Домой"]], resize_keyboard=True
    )
    await update.callback_query.message.reply_text(
        "Выберите тип выплаты:", reply_markup=keyboard
    )
    context.user_data["payout_data"].pop("payout_type", None)
    return PayoutStates.SELECT_TYPE


async def change_payout_method(update: Update,
                               context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    keyboard = ReplyKeyboardMarkup(
        [["💵 Из кассы", "💳 На карту"], ["🏠 Домой"]], resize_keyboard=True
    )
    await update.callback_query.message.reply_text(
        "Выберите способ получения выплаты:", reply_markup=keyboard
    )
    return PayoutStates.SELECT_METHOD
