"""Personal cabinet — VK port of app/handlers/user/cabinet.py (view info,
request phone/bank change with admin approval, request history). Uses the
existing Telegram-side admin approval flow via admin_bridge — the admin
still approves/rejects from Telegram/the web admin, only the employee side
of the round trip is VK."""

from __future__ import annotations

import re

from vkbottle.bot import Bot, Message

from app.config import MAX_ADVANCE_AMOUNT_PER_MONTH
from app.services.users import load_users_map, save_users
from app.services.advance_requests import load_advance_requests
from app.utils.logger import log
from ..admin_bridge import notify_admin_profile_change
from ..keyboards import cabinet_menu, edit_menu, confirm_menu, main_menu
from ..states import CabinetStates
import datetime


async def open_cabinet(message: Message, employee_id: str) -> None:
    users = load_users_map()
    user = users.get(employee_id)
    if not user:
        await message.answer("❌ Ваши данные не найдены. Обратитесь к администратору.", keyboard=main_menu(employee_id).get_json())
        return
    name = user.get("name", "Не указано")
    await message.answer(f"👤 Добро пожаловать в личный кабинет, {name}!\nВыберите действие:", keyboard=cabinet_menu().get_json())


async def view_info(message: Message, employee_id: str) -> None:
    users = load_users_map()
    user = users.get(employee_id)
    if not user:
        await message.answer("❌ Ваши данные не найдены.", keyboard=cabinet_menu().get_json())
        return
    info_text = (
        f"📋 Ваши данные:\n"
        f"Имя: {user.get('name', 'Не указано')}\n"
        f"ФИО: {user.get('full_name', 'Не указано')}\n"
        f"Телефон: {user.get('phone', 'Не указано')}\n"
        f"Банк: {user.get('bank', 'Не указано')}\n"
        f"🎂 День рождения: {user.get('birthdate', 'Не указано')}"
    )
    await message.answer(info_text, keyboard=cabinet_menu().get_json())


async def start_edit(bot: Bot, message: Message) -> None:
    await message.answer("✏️ Что вы хотите изменить?", keyboard=edit_menu().get_json())


async def handle_edit_field_choice(bot: Bot, message: Message, employee_id: str) -> bool:
    """Returns True if the message was a recognised edit-menu choice."""
    choice = (message.text or "").strip()
    if choice == "📱 Изменить телефон":
        field = "phone"
        prompt = "Введите новый номер телефона (11 цифр, например, 89012345678):"
    elif choice == "🏦 Изменить банк":
        field = "bank"
        prompt = "Введите название банка (до 50 символов, только буквы, цифры, пробелы):"
    else:
        return False
    await bot.state_dispenser.set(message.peer_id, CabinetStates.AWAITING_NEW_VALUE, field=field)
    await message.answer(prompt)
    return True


async def handle_new_value(bot: Bot, message: Message, employee_id: str, field: str) -> None:
    new_value = (message.text or "").strip()
    if field == "phone":
        if not re.match(r"^\d{11}$", new_value):
            await message.answer("❌ Номер телефона должен содержать ровно 11 цифр (например, 89012345678). Повторите ввод:")
            return
    elif field == "bank":
        if len(new_value) > 50 or not re.match(r"^[a-zA-Zа-яА-Я0-9\s]+$", new_value):
            await message.answer("❌ Название банка должно быть до 50 символов и содержать только буквы, цифры и пробелы. Повторите ввод:")
            return
    await bot.state_dispenser.set(
        message.peer_id, CabinetStates.AWAITING_EDIT_CONFIRM, field=field, new_value=new_value,
    )
    await message.answer(
        f"Новое значение для {field}: {new_value}\nПодтвердите изменение:",
        keyboard=confirm_menu().get_json(),
    )


async def handle_edit_confirmation(bot: Bot, message: Message, employee_id: str, field: str, new_value: str) -> None:
    choice = (message.text or "").strip()
    await bot.state_dispenser.delete(message.peer_id)
    if choice != "✅ Подтвердить":
        await message.answer("❌ Изменение отменено. Вы вернулись в личный кабинет.", keyboard=cabinet_menu().get_json())
        return

    users = load_users_map()
    if employee_id not in users:
        await message.answer("❌ Ваши данные не найдены.", keyboard=main_menu(employee_id).get_json())
        return
    users[employee_id]["pending_change"] = {"field": field, "value": new_value}
    save_users(users)
    log(f"DEBUG [vk/cabinet] Сохранено изменение для {employee_id}: {field} → {new_value}")

    await notify_admin_profile_change(employee_id, users[employee_id].get("name", ""), field, new_value)
    await message.answer(
        f"✅ Запрос на изменение {field} отправлен администратору на проверку.\nВы вернулись в личный кабинет.",
        keyboard=cabinet_menu().get_json(),
    )


async def view_history(message: Message, employee_id: str) -> None:
    try:
        requests_list = load_advance_requests()
        if not isinstance(requests_list, list):
            raise ValueError("bad shape")
    except Exception as e:
        log(f"❌ [vk/cabinet] Ошибка загрузки истории запросов для {employee_id}: {e}")
        await message.answer("❌ Ошибка загрузки истории запросов. Обратитесь к администратору.", keyboard=cabinet_menu().get_json())
        return

    user_requests = [r for r in requests_list if r["user_id"] == employee_id][-5:]
    current_month = datetime.datetime.now().strftime("%Y-%m")
    user_advance_requests = [
        r for r in requests_list
        if r["user_id"] == employee_id
        and r["status"] == "Одобрено"
        and r["timestamp"].startswith(current_month)
        and (r.get("payout_type") in ["Аванс", None] or "payout_type" not in r)
    ]
    total_advance_amount = sum(int(r.get("amount", 0)) for r in user_advance_requests)
    remaining_amount = MAX_ADVANCE_AMOUNT_PER_MONTH - total_advance_amount

    if not user_requests:
        await message.answer(
            f"📜 У вас пока нет запросов на выплату.\nАвансы за {current_month}: {total_advance_amount} ₽ из {MAX_ADVANCE_AMOUNT_PER_MONTH} ₽",
            keyboard=cabinet_menu().get_json(),
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
    await message.answer(history_text.strip(), keyboard=cabinet_menu().get_json())
