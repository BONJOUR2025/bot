"""Обработчики ручного создания выплат администратором."""

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import ContextTypes, ConversationHandler

from ...services.users import load_users
from ...keyboards.reply_admin import get_admin_menu
from ...services.advance_requests import log_new_request
from ...constants import ManualPayoutStates


async def manual_payout_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    users = load_users()
    employee_names = sorted(
        {u.get("name") for u in users.values() if u.get("name")}
    )
    keyboard = [[name] for name in employee_names] + [["🏠 Домой"]]
    context.user_data["manual_users"] = {
        v["name"]: uid for uid, v in users.items() if "name" in v
    }
    await update.message.reply_text(
        "Выберите сотрудника:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )
    return ManualPayoutStates.SELECT_EMPLOYEE


async def manual_payout_employee(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    name = update.message.text
    user_map = context.user_data.get("manual_users", {})
    if name not in user_map:
        await update.message.reply_text(
            "❌ Некорректный выбор. Попробуйте снова."
        )
        return ManualPayoutStates.SELECT_EMPLOYEE
    context.user_data["manual_payout"] = {
        "name": name,
        "user_id": user_map[name],
    }
    await update.message.reply_text(
        "Выберите тип выплаты:",
        reply_markup=ReplyKeyboardMarkup(
            [["Аванс", "Зарплата"], ["🏠 Домой"]], resize_keyboard=True
        ),
    )
    return ManualPayoutStates.SELECT_TYPE


async def manual_payout_type(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    payout_type = update.message.text
    context.user_data["manual_payout"]["payout_type"] = payout_type
    await update.message.reply_text("Введите сумму выплаты:")
    return ManualPayoutStates.ENTER_AMOUNT


async def manual_payout_amount(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ Введите корректную сумму.")
        return ManualPayoutStates.ENTER_AMOUNT
    context.user_data["manual_payout"]["amount"] = int(text)
    await update.message.reply_text(
        "Выберите способ:",
        reply_markup=ReplyKeyboardMarkup(
            [["💳 На карту", "💵 Из кассы"], ["🏠 Домой"]],
            resize_keyboard=True,
        ),
    )
    return ManualPayoutStates.SELECT_METHOD


async def manual_payout_method(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    method = update.message.text
    context.user_data["manual_payout"]["method"] = method
    data = context.user_data["manual_payout"]
    users = load_users()
    user = users.get(data["user_id"], {})
    data["phone"] = user.get("phone", "—")
    data["bank"] = user.get("bank", "—")

    msg = (
        f"📤 Создать запрос от имени:\n"
        f"👤 {data['name']}\n📱 {data['phone']}\n🏦 {data['bank']}\n\n"
        f"Тип: {data['payout_type']}\nСумма: {data['amount']} ₽\nМетод: {data['method']}"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Подтвердить", callback_data="manual_confirm"
                )
            ],
            [InlineKeyboardButton("❌ Отмена", callback_data="manual_cancel")],
        ]
    )
    await update.message.reply_text(msg, reply_markup=keyboard)
    return ManualPayoutStates.CONFIRM


async def manual_payout_finalize(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    if query.data == "manual_cancel":
        await query.edit_message_text("❌ Запрос отменён.")
        await query.bot.send_message(
            chat_id=query.message.chat.id,
            text="🏠 Возврат в меню администратора.",
            reply_markup=get_admin_menu(),
        )
        context.user_data.clear()
        return ConversationHandler.END

    data = context.user_data.get("manual_payout", {})
    log_new_request(
        data["user_id"],
        data["name"],
        data["phone"],
        data["bank"],
        data["amount"],
        data["method"],
        data["payout_type"],
    )
    await query.edit_message_text("✅ Запрос создан и сохранён.")
    await query.bot.send_message(
        chat_id=query.message.chat.id,
        text="🏠 Возврат в меню администратора.",
        reply_markup=get_admin_menu(),
    )
    context.user_data.clear()
    return ConversationHandler.END
