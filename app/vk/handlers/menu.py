"""Main menu, home, salary & schedule viewing — VK port of
app/handlers/user/home.py + app/handlers/user/menu.py."""

from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
from vkbottle.bot import Bot, Message

from app.config import EXCEL_FILE
from app.services.users import load_users_map
from app.services.excel import load_data
from app.services.report import generate_employee_report, generate_employee_report_from_payroll
from app.services.payroll_service import get_payroll_service
from app.services.config_service import ConfigService
from app.utils.image import create_schedule_image, create_combined_table_image, create_payroll_report_image
from app.utils.logger import log
from ..context import resolve_employee, send_photo
from ..keyboards import main_menu, month_keyboard
from ..states import MenuStates

VALID_MONTHS = [
    "ЯНВАРЬ", "ФЕВРАЛЬ", "МАРТ", "АПРЕЛЬ", "МАЙ", "ИЮНЬ",
    "ИЮЛЬ", "АВГУСТ", "СЕНТЯБРЬ", "ОКТЯБРЬ", "НОЯБРЬ", "ДЕКАБРЬ",
]


def _use_sql_source() -> bool:
    value = ConfigService().load().get("salary_bot_source", "excel")
    return str(value).strip().lower() == "sql"


async def send_main_menu(message: Message, employee_id: str, name: str = "") -> None:
    greeting = f"Приветствую тебя, {name}!\n\nВыберите действие:" if name else "Выберите действие:"
    await message.answer(greeting, keyboard=main_menu(employee_id).get_json())


async def prompt_salary_month(bot: Bot, message: Message) -> None:
    await bot.state_dispenser.set(message.peer_id, MenuStates.AWAITING_MONTH_SALARY)
    await message.answer("📅 Выберите месяц для просмотра ЗП:", keyboard=month_keyboard().get_json())


async def prompt_schedule_month(bot: Bot, message: Message) -> None:
    await bot.state_dispenser.set(message.peer_id, MenuStates.AWAITING_MONTH_SCHEDULE)
    await message.answer("📅 Выберите месяц для просмотра расписания:", keyboard=month_keyboard().get_json())


async def handle_month_selected(bot: Bot, message: Message, employee_id: str, requested: str) -> None:
    month = (message.text or "").strip().upper()
    if month not in VALID_MONTHS:
        await message.answer("❌ Неверный месяц. Выберите из предложенных.", keyboard=month_keyboard().get_json())
        return

    await bot.state_dispenser.delete(message.peer_id)
    users = load_users_map()
    user = users.get(employee_id)
    if not user:
        await message.answer(
            "❌ Информация о пользователе не найдена. Обратитесь к администратору.",
            keyboard=main_menu(employee_id).get_json(),
        )
        return
    user_name = (user.get("name") or "").strip()
    user_name_lower = user_name.lower()

    await message.answer("⏳ Загружаю данные...")

    if requested == "salary":
        report_tables = None
        from_sql = False
        if _use_sql_source():
            payroll = get_payroll_service()
            code = payroll.get_code_for_employee(employee_id=employee_id, full_name=user_name)
            if code:
                year = datetime.now().year
                row = await payroll.get_employee_details(code, month, year)
                if row:
                    report_tables = generate_employee_report_from_payroll(row, month)
                    from_sql = True

        if report_tables is None:
            try:
                data = load_data(sheet_name=month)
                if data is None or "ИМЯ" not in data.columns:
                    await message.answer(f"❌ Ошибка загрузки данных для {month}.", keyboard=main_menu(employee_id).get_json())
                    return
            except Exception as e:
                log(f"❌ [vk/menu] Ошибка чтения Excel: {e}")
                await message.answer(f"❌ Ошибка загрузки данных для {month}: {e}", keyboard=main_menu(employee_id).get_json())
                return
            data["ИМЯ"] = data["ИМЯ"].astype(str).str.strip().str.lower()
            employee_data = data[data["ИМЯ"] == user_name_lower]
            if employee_data.empty:
                await message.answer(
                    f"❌ Данные за {month} для {user_name} не найдены. Обратитесь к руководителю.",
                    keyboard=main_menu(employee_id).get_json(),
                )
                return
            row_index = employee_data.index[0]
            report_tables = generate_employee_report(user_name, month, data, row_index)

        filename = (
            create_payroll_report_image(report_tables, f"salary_report_vk_{employee_id}.png")
            if from_sql
            else create_combined_table_image(report_tables, f"salary_report_vk_{employee_id}.png")
        )
        if filename and os.path.exists(filename):
            await send_photo(message, filename, "Ваш отчет о зарплате", main_menu(employee_id))
        else:
            await message.answer("❌ Не удалось создать изображение отчёта.", keyboard=main_menu(employee_id).get_json())

    elif requested == "schedule":
        try:
            raw_data = pd.read_excel(EXCEL_FILE, sheet_name=month, header=None)
            if raw_data.shape[0] < 2 or raw_data.shape[1] < 3:
                await message.answer(f"❌ Неверная структура данных в Excel для {month}.", keyboard=main_menu(employee_id).get_json())
                return
        except Exception as e:
            log(f"❌ [vk/menu] Ошибка чтения Excel: {e}")
            await message.answer(f"❌ Ошибка загрузки данных для {month}: {e}", keyboard=main_menu(employee_id).get_json())
            return
        first_row = raw_data.iloc[0].tolist()
        weekdays_row = raw_data.iloc[1].tolist()
        raw_data.columns = first_row[:2] + [str(val) for val in first_row[2:]]
        raw_data = raw_data.drop([0, 1]).reset_index(drop=True)
        raw_data["ИМЯ"] = raw_data["ИМЯ"].astype(str).str.strip().str.lower()
        employee_data = raw_data[raw_data["ИМЯ"] == user_name_lower]
        if employee_data.empty:
            await message.answer(
                f"❌ Данные за {month} для {user_name} не найдены. Обратитесь к руководителю.",
                keyboard=main_menu(employee_id).get_json(),
            )
            return
        filename = create_schedule_image(raw_data, user_name, month, weekdays_row[2:33])
        if filename and os.path.exists(filename):
            await send_photo(message, filename, "Ваше расписание", main_menu(employee_id))
        else:
            await message.answer("❌ Не удалось создать изображение расписания.", keyboard=main_menu(employee_id).get_json())
