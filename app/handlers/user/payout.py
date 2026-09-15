from __future__ import annotations

import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from ...constants import PAYMENT_REQUEST_PATTERN, PayoutStates
from ...core.constants import PAYOUT_TYPES
from ...config import MAX_ADVANCE_AMOUNT_PER_MONTH
from ...services.users import load_users_map
from ...services.advance_requests import (
    check_pending_request,
    load_advance_requests,
    log_new_request,
)
from ...services.telegram_service import TelegramService
from app.data.employee_repository import EmployeeRepository
from ...utils.logger import log


def _rub(value: float) -> str:
    return f"{float(value):,.0f} ₽".replace(",", " ")


async def _master_advance_cap(user_id: str) -> dict | None:
    """Сколько мастер уже заработал и сколько может взять авансом.

    None означает «потолок неизвестен» — сотрудник не мастер, либо отчёт
    сейчас не посчитать. Намеренно fail-open: Firebird бывает занят, и
    заблокировать в такой момент все заявки на аванс — куда хуже, чем
    пропустить заявку без проверки, которую всё равно утверждает админ.
    """
    try:
        from ...services.firebird_service import run_with_timeout
        from ...services.master_bot_service import get_advance_cap, resolve_master

        master = resolve_master(user_id)
        if master is None:
            return None
        return await run_with_timeout(get_advance_cap, master, timeout=55)
    except Exception as exc:
        log(f"⚠️ [payout] не удалось посчитать потолок аванса для {user_id}: {exc}")
        return None


async def request_payout_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PayoutStates:
    """Start payout request conversation."""
    chat_id = update.effective_chat.id
    state = context.application.chat_data.get(chat_id, {}).get("conversation")
    log(f"[FSM] state before entry: {state}")

    user_id = str(update.effective_user.id)

    if check_pending_request(user_id):
        await update.message.reply_text(
            "❗ У вас уже есть необработанный запрос. Дождитесь его обработки.",
            reply_markup=ReplyKeyboardMarkup([["🏠 Домой"]], resize_keyboard=True),
        )
        return ConversationHandler.END

    users = load_users_map()
    user = users.get(user_id)
    if not user:
        await update.message.reply_text(
            "❌ Ваши данные не найдены. Обратитесь к администратору.",
            reply_markup=ReplyKeyboardMarkup([["🏠 Домой"]], resize_keyboard=True),
        )
        return ConversationHandler.END

    if not user.get("card_number"):
        await update.message.reply_text(
            "❌ У вас не указан номер карты. Пожалуйста, обратитесь к администратору.",
            reply_markup=ReplyKeyboardMarkup([["🏠 Домой"]], resize_keyboard=True),
        )
        return ConversationHandler.END

    context.user_data["payout_data"] = {
        "user_id": user_id,
        "name": user.get("name", ""),
        "phone": user.get("phone", ""),
        "bank": user.get("bank", ""),
        "card_number": user.get("card_number", ""),
    }
    context.user_data["payout_in_progress"] = True

    keyboard = ReplyKeyboardMarkup(
        [PAYOUT_TYPES, ["🏠 Домой"]], resize_keyboard=True
    )
    await update.message.reply_text(
        "Выберите тип выплаты:", reply_markup=keyboard
    )
    return PayoutStates.SELECT_TYPE


async def select_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PayoutStates:
    payout_type = update.message.text.strip()
    if payout_type not in PAYOUT_TYPES:
        await update.message.reply_text(
            "❌ Пожалуйста, выберите из предложенных вариантов."
        )
        return PayoutStates.SELECT_TYPE
    data = context.user_data.setdefault("payout_data", {})
    data["payout_type"] = payout_type

    prompt = "Введите сумму:"
    if payout_type == "Аванс":
        cap = await _master_advance_cap(str(update.effective_user.id))
        if cap is not None:
            data["advance_cap"] = cap["available"]
            # Начисление — за текущий месяц (get_advance_cap), а авансы — с
            # последней зарплаты; подпись раньше путала первое со вторым.
            earned_label = (
                "Стипендия за этот месяц"
                if cap["basis"] == "stipend"
                else "Начислено за этот месяц"
            )
            prompt = (
                f"{earned_label}: {_rub(cap['earned'])}\n"
                f"Уже взято авансом: {_rub(cap['advances'])}\n"
                f"<b>Доступно к авансу: {_rub(cap['available'])}</b>\n\n"
                "Введите сумму:"
            )
            await update.message.reply_text(prompt, parse_mode="HTML")
            return PayoutStates.ENTER_AMOUNT

    await update.message.reply_text(prompt)
    return PayoutStates.ENTER_AMOUNT


async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PayoutStates:
    text = update.message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("❌ Введите положительное целое число.")
        return PayoutStates.ENTER_AMOUNT

    amount = int(text)
    data = context.user_data.setdefault("payout_data", {})
    user_id = data.get("user_id")

    # Потолок мастера: больше заработанного авансом не выдаём. Считается
    # один раз при входе в флоу (см. _master_advance_cap) — если посчитать
    # не удалось, ключа здесь просто нет и проверка не срабатывает.
    if data.get("payout_type") == "Аванс" and data.get("advance_cap") is not None:
        cap = float(data["advance_cap"])
        if amount > cap:
            await update.message.reply_text(
                f"❌ Это больше, чем вы заработали.\n"
                f"Доступно к авансу: {_rub(cap)}\n\nВведите другую сумму:"
            )
            return PayoutStates.ENTER_AMOUNT

    # check monthly limit for advances
    if data.get("payout_type") == "Аванс":
        now_month = datetime.datetime.now().strftime("%Y-%m")
        requests = load_advance_requests()
        total = sum(
            int(r.get("amount", 0))
            for r in requests
            if r.get("user_id") == user_id
            and r.get("timestamp", "").startswith(now_month)
            and r.get("status") in {"Одобрено", "Ожидает"}
            and (r.get("payout_type") in ["Аванс", None] or "payout_type" not in r)
        )
        if total + amount > MAX_ADVANCE_AMOUNT_PER_MONTH:
            await update.message.reply_text(
                "❌ Превышен месячный лимит авансов.",
                reply_markup=ReplyKeyboardMarkup([["🏠 Домой"]], resize_keyboard=True),
            )
            context.user_data.clear()
            return ConversationHandler.END

    data["amount"] = amount
    keyboard = ReplyKeyboardMarkup(
        [["💳 На карту", "🏦 Из кассы", "🤝 Наличными"], ["🏠 Домой"]],
        resize_keyboard=True,
    )
    await update.message.reply_text(
        "Выберите способ получения:", reply_markup=keyboard
    )
    return PayoutStates.SELECT_METHOD


async def select_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PayoutStates:
    method = update.message.text.strip()
    if method not in {"💳 На карту", "🏦 Из кассы", "🤝 Наличными"}:
        await update.message.reply_text(
            "❌ Пожалуйста, выберите из предложенных вариантов."
        )
        return PayoutStates.SELECT_METHOD

    data = context.user_data.setdefault("payout_data", {})
    data["method"] = method

    text = (
        f"Тип: {data.get('payout_type')}\n"
        f"Сумма: {data.get('amount')} ₽\n"
        f"Метод: {method}"
    )
    if method == "💳 На карту":
        card = data.get("card_number") or "—"
        bank = data.get("bank") or "—"
        text = f"Карта: {card}\nБанк: {bank}\n\n" + text

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Подтвердить", callback_data="payout_confirm")],
            [InlineKeyboardButton("❌ Отмена", callback_data="payout_cancel")],
        ]
    )
    await update.message.reply_text(text, reply_markup=keyboard)
    return PayoutStates.CONFIRM_CARD


async def confirm_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()
    data = context.user_data.get("payout_data", {})

    if query.data == "payout_cancel":
        await query.edit_message_text("❌ Запрос отменён.")
        context.user_data.clear()
        return ConversationHandler.END

    record = log_new_request(
        data.get("user_id"),
        data.get("name", ""),
        data.get("phone", ""),
        data.get("card_number", ""),
        data.get("bank", ""),
        data.get("amount"),
        data.get("method"),
        data.get("payout_type"),
    )

    telegram_service = TelegramService(EmployeeRepository(), bot=context.application.bot)
    try:
        await telegram_service.send_payout_request_to_admin(record)
    except Exception as exc:
        log(f"❌ Failed to notify admin: {exc}")

    await query.edit_message_text("✅ Запрос отправлен администратору.")
    context.user_data.clear()
    return ConversationHandler.END
