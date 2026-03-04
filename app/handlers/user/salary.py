import os
from datetime import datetime

import pandas as pd
from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional

from ...utils.image import create_combined_table_image
from ...services.report import generate_employee_report, generate_employee_report_from_payroll
from ...services.excel import load_data
from ...services.users import load_users_map
from ...services.payroll_service import get_payroll_service
from ...services.config_service import ConfigService
from ...utils.logger import log


def _use_sql_source() -> bool:
    """Читает SALARY_BOT_SOURCE из config.json при каждом запросе (без перезапуска)."""
    value = ConfigService().load().get("salary_bot_source", "excel")
    return str(value).strip().lower() == "sql"


async def handle_salary_request(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Обрабатывает запрос зарплаты для пользователя."""
    if not update.message:
        return

    month: str = update.message.text.strip().upper()
    user_id: str = str(update.effective_user.id)
    valid_months = [
        "ЯНВАРЬ",
        "ФЕВРАЛЬ",
        "МАРТ",
        "АПРЕЛЬ",
        "МАЙ",
        "ИЮНЬ",
        "ИЮЛЬ",
        "АВГУСТ",
        "СЕНТЯБРЬ",
        "ОКТЯБРЬ",
        "НОЯБРЬ",
        "ДЕКАБРЬ",
    ]

    log(
        f"📌 [handle_salary_request] Пользователь {user_id} выбрал месяц: {month}"
    )

    if month not in valid_months:
        await update.message.reply_text(
            "❌ Неверный месяц. Выберите из предложенных."
        )
        return

    loading_message = await update.message.reply_text(
        "⏳ Подождите, считаю денежки..."
    )

    await context.bot.send_chat_action(
        chat_id=update.message.chat_id, action="typing"
    )

    use_sql = _use_sql_source()

    if use_sql:
        report_tables = await _handle_salary_sql(user_id, month)
    else:
        report_tables = _handle_salary_excel(user_id, month)

    if report_tables is None:
        await loading_message.edit_text(
            f"❌ Данные за {month} не найдены. Обратитесь к руководителю."
        )
        return

    filename = create_combined_table_image(
        report_tables, f"salary_report_{user_id}.png"
    )

    if filename and os.path.exists(filename):
        try:
            await loading_message.delete()
        except Exception as e:
            log(f"⚠️ Ошибка удаления сообщения: {e}")
        with open(filename, "rb") as photo:
            await update.message.reply_photo(photo=photo)
    else:
        await loading_message.edit_text(
            "❌ Не удалось сгенерировать изображение отчёта."
        )


def _handle_salary_excel(user_id: str, month: str):
    """Загружает данные из Excel и возвращает таблицы отчёта."""
    data: Optional[pd.DataFrame] = load_data(sheet_name=month)
    if data is None or "ИМЯ" not in data.columns:
        log(f"❌ [excel] Ошибка загрузки данных для месяца {month}")
        return None

    users = load_users_map()
    user = users.get(user_id)
    if not user:
        log(f"❌ [excel] Пользователь {user_id} не найден")
        return None

    user_name: str = user.get("name")
    log(f"✅ [excel] Пользователь найден: {user_name}")

    data["ИМЯ"] = data["ИМЯ"].astype(str).str.strip()
    employee_data = data[data["ИМЯ"] == user_name]

    if employee_data.empty:
        log(f"❌ [excel] Данные за {month} для {user_name} не найдены")
        return None

    row_index = employee_data.index[0]
    return generate_employee_report(user_name, month, data, row_index)


async def _handle_salary_sql(user_id: str, month: str):
    """Загружает данные из SQL (Firebird) через PayrollService и возвращает таблицы отчёта."""
    payroll = get_payroll_service()

    employee_code = payroll._user_id_to_code.get(user_id)
    if not employee_code:
        log(f"❌ [sql] Код сотрудника для user_id={user_id} не найден")
        return None

    year = datetime.now().year
    row = await payroll.get_employee_details(employee_code, month, year)
    if row is None:
        log(f"❌ [sql] Данные за {month} для кода {employee_code} не найдены")
        return None

    log(f"✅ [sql] Данные получены: {row.employee_name}")
    return generate_employee_report_from_payroll(row, month)
