"""Payout request FSM — VK port of app/handlers/user/payout.py. Confirmation
is a plain reply-keyboard step (see keyboards.py's note) instead of an
inline callback button."""

from __future__ import annotations

import datetime

from vkbottle.bot import Bot, Message

from app.config import MAX_ADVANCE_AMOUNT_PER_MONTH
from app.services.users import load_users_map
from app.services.advance_requests import check_pending_request, load_advance_requests, log_new_request
from app.services.telegram_service import TelegramService
from app.data.employee_repository import EmployeeRepository
from app.utils.logger import log
from ..keyboards import home_only_menu, payout_type_menu, payout_method_menu, confirm_menu, main_menu
from ..states import PayoutStates

PAYOUT_TYPES = {"Аванс", "Зарплата"}
PAYOUT_METHODS = {"💳 На карту", "🏦 Из кассы", "🤝 Наличными"}


async def start_payout(bot: Bot, message: Message, employee_id: str) -> None:
    if check_pending_request(employee_id):
        await message.answer("❗ У вас уже есть необработанный запрос. Дождитесь его обработки.", keyboard=home_only_menu().get_json())
        return

    users = load_users_map()
    user = users.get(employee_id)
    if not user:
        await message.answer("❌ Ваши данные не найдены. Обратитесь к администратору.", keyboard=home_only_menu().get_json())
        return
    if not user.get("card_number"):
        await message.answer("❌ У вас не указан номер карты. Пожалуйста, обратитесь к администратору.", keyboard=home_only_menu().get_json())
        return

    payload = {
        "name": user.get("name", ""),
        "phone": user.get("phone", ""),
        "bank": user.get("bank", ""),
        "card_number": user.get("card_number", ""),
    }
    await bot.state_dispenser.set(message.peer_id, PayoutStates.SELECT_TYPE, **payload)
    await message.answer("Выберите тип выплаты:", keyboard=payout_type_menu().get_json())


async def select_type(bot: Bot, message: Message, employee_id: str, payload: dict) -> None:
    payout_type = (message.text or "").strip()
    if payout_type not in PAYOUT_TYPES:
        await message.answer("❌ Пожалуйста, выберите из предложенных вариантов.", keyboard=payout_type_menu().get_json())
        return
    await bot.state_dispenser.set(message.peer_id, PayoutStates.ENTER_AMOUNT, **{**payload, "payout_type": payout_type})
    await message.answer("Введите сумму:")


async def enter_amount(bot: Bot, message: Message, employee_id: str, payload: dict) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("❌ Введите положительное целое число.")
        return
    amount = int(text)

    if payload.get("payout_type") == "Аванс":
        now_month = datetime.datetime.now().strftime("%Y-%m")
        requests = load_advance_requests()
        total = sum(
            int(r.get("amount", 0))
            for r in requests
            if r.get("user_id") == employee_id
            and r.get("timestamp", "").startswith(now_month)
            and r.get("status") in {"Одобрено", "Ожидает"}
            and (r.get("payout_type") in ["Аванс", None] or "payout_type" not in r)
        )
        if total + amount > MAX_ADVANCE_AMOUNT_PER_MONTH:
            await bot.state_dispenser.delete(message.peer_id)
            await message.answer("❌ Превышен месячный лимит авансов.", keyboard=main_menu(employee_id).get_json())
            return

    await bot.state_dispenser.set(message.peer_id, PayoutStates.SELECT_METHOD, **{**payload, "amount": amount})
    await message.answer("Выберите способ получения:", keyboard=payout_method_menu().get_json())


async def select_method(bot: Bot, message: Message, employee_id: str, payload: dict) -> None:
    method = (message.text or "").strip()
    if method not in PAYOUT_METHODS:
        await message.answer("❌ Пожалуйста, выберите из предложенных вариантов.", keyboard=payout_method_menu().get_json())
        return

    text = (
        f"Тип: {payload.get('payout_type')}\n"
        f"Сумма: {payload.get('amount')} ₽\n"
        f"Метод: {method}"
    )
    if method == "💳 На карту":
        card = payload.get("card_number") or "—"
        bank = payload.get("bank") or "—"
        text = f"Карта: {card}\nБанк: {bank}\n\n" + text

    await bot.state_dispenser.set(message.peer_id, PayoutStates.CONFIRM, **{**payload, "method": method})
    await message.answer(text, keyboard=confirm_menu().get_json())


async def confirm(bot: Bot, message: Message, employee_id: str, payload: dict) -> None:
    choice = (message.text or "").strip()
    await bot.state_dispenser.delete(message.peer_id)
    if choice != "✅ Подтвердить":
        await message.answer("❌ Запрос отменён.", keyboard=main_menu(employee_id).get_json())
        return

    record = log_new_request(
        employee_id,
        payload.get("name", ""),
        payload.get("phone", ""),
        payload.get("card_number", ""),
        payload.get("bank", ""),
        payload.get("amount"),
        payload.get("method"),
        payload.get("payout_type"),
    )

    telegram_service = TelegramService(EmployeeRepository())
    try:
        await telegram_service.send_payout_request_to_admin(record)
    except Exception as exc:
        log(f"❌ [vk/payout] Failed to notify admin: {exc}")

    await message.answer("✅ Запрос отправлен администратору.", keyboard=main_menu(employee_id).get_json())
