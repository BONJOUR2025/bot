import os
import pandas as pd
from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional
from ...utils.image import create_combined_table_image
from ...services.report import generate_employee_report
from ...services.excel import load_data
from ...services.users import load_users_map
from ...utils.logger import log


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

    data: Optional[pd.DataFrame] = load_data(sheet_name=month)
    if data is None or "ИМЯ" not in data.columns:
        await loading_message.edit_text(
            f"❌ Ошибка загрузки данных для месяца {month}."
        )
        return

    users = load_users_map()
    user = users.get(user_id)
    if not user:
        await loading_message.edit_text(
            "❌ Информация о пользователе не найдена. Обратитесь к администратору."
        )
        return

    user_name: str = user.get("name")
    log(f"✅ [handle_salary_request] Пользователь найден: {user_name}")

    # Фильтрация данных по имени сотрудника
    data["ИМЯ"] = data["ИМЯ"].astype(str).str.strip()
    employee_data = data[data["ИМЯ"] == user_name]

    if employee_data.empty:
        await loading_message.edit_text(
            f"❌ Данные за {month} для {user_name} не найдены. Обратитесь к руководителю."
        )
        return

    row_index = employee_data.index[0]

    # Генерация отчёта
    report_tables = generate_employee_report(user_name, month, data, row_index)

    # Создание изображения отчёта
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
