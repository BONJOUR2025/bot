"""Entrypoint for running the VK bot — a third process alongside app.main
(Telegram) and uvicorn (API/admin).

Ports the core employee-facing Telegram scenarios (main menu, salary/
schedule viewing, personal cabinet, payout request, open-salon shift
check-in) onto vkbottle. Deliberately NOT ported here (see the chat for the
full reasoning):
  - the in-bot admin scenarios (data view, payouts view, broadcast, manual
    payout, advance report) — the web admin already covers all of these
    more capably; admin keeps using Telegram/the web admin.
  - the HR/LLM recruitment layer (business_connection, interview_decision,
    quick_task, vacancy_setup, knowledge_base) — a distinct module, lower
    priority, business_connection specifically is a Telegram Business API
    feature with no VK equivalent.

IMPORTANT: this code has not been run against a live VK bot — there is no
VK community/token yet (VK_API_TOKEN unset), and vkbottle isn't installed
in this environment, so it could only be reviewed, not executed or tested.
Treat the first real run as a testing pass, not a formality.

Requires VK_API_TOKEN in .env (community/group access token, `messages`
scope). Uses VK's Bot Long Poll API — no public webhook URL needed, same
long-polling model as the Telegram bot.
"""

from __future__ import annotations

from vkbottle.bot import Bot, Message

from .config import VK_API_TOKEN
from .data.vk_bot_user_repository import get_vk_bot_user_repository
from .services.users import load_users_map
from .utils.logger import log, log_connection
from .vk.context import resolve_employee
from .vk.keyboards import main_menu
from .vk.states import MenuStates, CabinetStates, PayoutStates, ShiftCheckinStates
from .vk.handlers import menu as h_menu
from .vk.handlers import cabinet as h_cabinet
from .vk.handlers import payout as h_payout
from .vk.handlers import shift_checkin as h_shift

bot = Bot(token=VK_API_TOKEN)

HOME_TEXTS = {"🏠 домой", "домой", "🏠домой"}

# Main-menu button texts (see app/services/access_control_service.py's
# BOT_BUTTON_CATALOG — kept as literal strings here the same way Telegram's
# application.py registers them as literal regex/text filters, not by
# importing the catalog, to avoid coupling VK's router to its internal shape).
BTN_SALARY = "📄 Просмотр ЗП"
BTN_SCHEDULE = "📅 Просмотр расписания"
BTN_PROFILE = "👤 Личный кабинет"
BTN_PAYOUT = "💰 Запросить выплату"
BTN_OPEN_SALON = "🏪 Открыть салон"

# Cabinet submenu
BTN_MY_INFO = "📋 Мои данные"
BTN_EDIT_INFO = "✏️ Изменить данные"
BTN_HISTORY = "📜 История запросов"


async def _register_contact(message: Message) -> None:
    screen_name = first_name = last_name = None
    try:
        users = await bot.api.users.get(user_ids=[message.from_id], fields=["screen_name"])
        if users:
            user = users[0]
            screen_name = getattr(user, "screen_name", None)
            first_name = getattr(user, "first_name", None)
            last_name = getattr(user, "last_name", None)
    except Exception as exc:
        log(f"⚠️ [vk_bot] Не удалось получить профиль {message.from_id}: {exc}")
    get_vk_bot_user_repository().touch(
        message.from_id, screen_name=screen_name, first_name=first_name, last_name=last_name,
    )


@bot.on.message()
async def route_message(message: Message) -> None:
    await _register_contact(message)

    employee = resolve_employee(message.from_id)
    if not employee:
        await message.answer(
            "❌ Ваш профиль не найден. Обратитесь к администратору, чтобы он привязал этот аккаунт "
            "ВКонтакте к вашему профилю в разделе «Доступы»."
        )
        return
    employee_id = employee.id
    text = (message.text or "").strip()

    # "Домой" always wins, regardless of any in-progress FSM state — mirrors
    # the Telegram fallback pattern (regex "Домой|Назад|Отмена" resets any
    # active ConversationHandler).
    if text.lower() in HOME_TEXTS:
        await bot.state_dispenser.delete(message.peer_id)
        users = load_users_map()
        name = (users.get(employee_id) or {}).get("name", "")
        greeting = f"Приветствую тебя, {name}!\n\nВыберите действие:" if name else "🏠 Вы вернулись в главное меню."
        await message.answer(greeting, keyboard=main_menu(employee_id).get_json())
        return

    state_peer = await bot.state_dispenser.get(message.peer_id)
    state = state_peer.state if state_peer else None
    payload = state_peer.payload if state_peer else {}

    # ── Active FSM takes priority over menu-button matching ──────────────
    if state == MenuStates.AWAITING_MONTH_SALARY:
        await h_menu.handle_month_selected(bot, message, employee_id, "salary")
        return
    if state == MenuStates.AWAITING_MONTH_SCHEDULE:
        await h_menu.handle_month_selected(bot, message, employee_id, "schedule")
        return

    if state == CabinetStates.AWAITING_NEW_VALUE:
        await h_cabinet.handle_new_value(bot, message, employee_id, payload.get("field"))
        return
    if state == CabinetStates.AWAITING_EDIT_CONFIRM:
        await h_cabinet.handle_edit_confirmation(bot, message, employee_id, payload.get("field"), payload.get("new_value"))
        return

    if state == PayoutStates.SELECT_TYPE:
        await h_payout.select_type(bot, message, employee_id, payload)
        return
    if state == PayoutStates.ENTER_AMOUNT:
        await h_payout.enter_amount(bot, message, employee_id, payload)
        return
    if state == PayoutStates.SELECT_METHOD:
        await h_payout.select_method(bot, message, employee_id, payload)
        return
    if state == PayoutStates.CONFIRM:
        await h_payout.confirm(bot, message, employee_id, payload)
        return

    if state == ShiftCheckinStates.AWAITING_PHOTO:
        await h_shift.handle_photo(bot, message, employee_id, employee.full_name or employee.name)
        return

    # ── No active FSM — treat as a top-level menu button ─────────────────
    if text == BTN_SALARY:
        await h_menu.prompt_salary_month(bot, message)
    elif text == BTN_SCHEDULE:
        await h_menu.prompt_schedule_month(bot, message)
    elif text == BTN_PROFILE:
        await h_cabinet.open_cabinet(message, employee_id)
    elif text == BTN_PAYOUT:
        await h_payout.start_payout(bot, message, employee_id)
    elif text == BTN_OPEN_SALON:
        await h_shift.start_open_salon(bot, message, employee_id)
    elif text == BTN_MY_INFO:
        await h_cabinet.view_info(message, employee_id)
    elif text == BTN_EDIT_INFO:
        await h_cabinet.start_edit(bot, message)
    elif text == BTN_HISTORY:
        await h_cabinet.view_history(message, employee_id)
    elif await h_cabinet.handle_edit_field_choice(bot, message, employee_id):
        pass  # handled inline (set AWAITING_NEW_VALUE state + prompted)
    else:
        users = load_users_map()
        name = (users.get(employee_id) or {}).get("name", "")
        await h_menu.send_main_menu(message, employee_id, name)


def main() -> None:
    if not VK_API_TOKEN:
        log("⚠️ VK_API_TOKEN не задан в .env — VK-бот не запущен")
        return
    log("🚀 VK bot started and waiting for messages...")
    log_connection("VK bot process started (long poll)")
    bot.run()


if __name__ == "__main__":
    main()
