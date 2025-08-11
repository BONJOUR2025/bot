import os
import pandas as pd
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from ...config import EXCEL_FILE
from ...services.users import load_users_map
from ...keyboards.reply_user import get_month_keyboard_user, get_main_menu
from ...utils.image import create_schedule_image, create_combined_table_image
from ...services.excel import load_data
from ...services.report import generate_employee_report
from ...utils.logger import log


async def view_salary_user(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запрашивает месяц для просмотра зарплаты."""
    chat_id = update.effective_chat.id
    state = context.application.chat_data.get(chat_id, {}).get("conversation")
    log(f"[FSM] state before entry: {state}")
    context.user_data["requested_data"] = "salary"
    if update.message:
        await update.message.reply_text(
            "📅 Выберите месяц для просмотра ЗП:",
            reply_markup=get_month_keyboard_user(),
        )
    return ConversationHandler.END


async def view_schedule_user(update: Update,
                             context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запрашивает месяц для просмотра расписания."""
    chat_id = update.effective_chat.id
    state = context.application.chat_data.get(chat_id, {}).get("conversation")
    log(f"[FSM] state before entry: {state}")
    context.user_data["requested_data"] = "schedule"
    if update.message:
        await update.message.reply_text(
            "📅 Выберите месяц для просмотра расписания:",
            reply_markup=get_month_keyboard_user(),
        )
    return ConversationHandler.END


async def handle_selected_month_user(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает выбор месяца для ЗП или расписания."""
    if not update.message:
        return
    month = update.message.text.strip().upper()
    user_id = str(update.effective_user.id)
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
        f"📌 [handle_selected_month_user] Пользователь {user_id} выбрал месяц: {month}")
    if month not in valid_months:
        await update.message.reply_text(
            "❌ Неверный месяц. Выберите из предложенных.",
            reply_markup=get_main_menu(),
        )
        return

    loading_message = await update.message.reply_text("⏳ Загружаю данные...")
    await context.bot.send_chat_action(chat_id=update.message.chat_id, action="typing")

    users = load_users_map()
    user = users.get(user_id)
    if not user:
        await loading_message.edit_text(
            "❌ Информация о пользователе не найдена. Обратитесь к администратору.",
            reply_markup=get_main_menu(),
        )
        return
    user_name = user.get("name", "").strip()
    user_name_lower = user_name.lower()

    requested_data = context.user_data.get("requested_data", "")
    if requested_data == "salary":
        try:
            data = load_data(sheet_name=month)
            if data is None or "ИМЯ" not in data.columns:
                log(
                    f"❌ [handle_selected_month_user] Неверная структура данных для {month}")
                await loading_message.edit_text(
                    f"❌ Ошибка загрузки данных для {month}.",
                    reply_markup=get_main_menu(),
                )
                return
        except Exception as e:
            log(f"❌ [handle_selected_month_user] Ошибка чтения Excel: {e}")
            await loading_message.edit_text(
                f"❌ Ошибка загрузки данных для {month}: {e}",
                reply_markup=get_main_menu(),
            )
            return

        data["ИМЯ"] = data["ИМЯ"].astype(str).str.strip().str.lower()
        employee_data = data[data["ИМЯ"] == user_name_lower]
        if employee_data.empty:
            await loading_message.edit_text(
                f"❌ Данные за {month} для {user_name} не найдены. Обратитесь к руководителю.",
                reply_markup=get_main_menu(),
            )
            return

        row_index = employee_data.index[0]
        report_tables = generate_employee_report(
            user_name, month, data, row_index)
        filename = create_combined_table_image(
            report_tables, f"salary_report_{user_id}.png")
        if filename and os.path.exists(filename):
            try:
                await loading_message.delete()
            except Exception as e:
                log(
                    f"⚠️ [handle_selected_month_user] Ошибка удаления сообщения: {e}")
            with open(filename, "rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption="Ваш отчет о зарплате",
                    reply_markup=get_main_menu(),
                )
        else:
            await loading_message.edit_text(
                "❌ Не удалось создать изображение отчёта.",
                reply_markup=get_main_menu(),
            )
    elif requested_data == "schedule":
        try:
            raw_data = pd.read_excel(EXCEL_FILE, sheet_name=month, header=None)
            if raw_data.shape[0] < 2 or raw_data.shape[1] < 3:
                await loading_message.edit_text(
                    f"❌ Неверная структура данных в Excel для {month}.",
                    reply_markup=get_main_menu(),
                )
                return
        except Exception as e:
            log(f"❌ [handle_selected_month_user] Ошибка чтения Excel: {e}")
            await loading_message.edit_text(
                f"❌ Ошибка загрузки данных для {month}: {e}",
                reply_markup=get_main_menu(),
            )
            return
        first_row = raw_data.iloc[0].tolist()
        weekdays_row = raw_data.iloc[1].tolist()
        raw_data.columns = first_row[:2] + [str(val) for val in first_row[2:]]
        raw_data = raw_data.drop([0, 1]).reset_index(drop=True)
        raw_data["ИМЯ"] = raw_data["ИМЯ"].astype(str).str.strip().str.lower()
        employee_data = raw_data[raw_data["ИМЯ"] == user_name_lower]
        if employee_data.empty:
            await loading_message.edit_text(
                f"❌ Данные за {month} для {user_name} не найдены. Обратитесь к руководителю.",
                reply_markup=get_main_menu(),
            )
            return
        filename = create_schedule_image(
            raw_data, user_name, month, weekdays_row[2:33])
        if filename and os.path.exists(filename):
            try:
                await loading_message.delete()
            except Exception as e:
                log(
                    f"⚠️ [handle_selected_month_user] Ошибка удаления сообщения: {e}")
            with open(filename, "rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption="Ваше расписание",
                    reply_markup=get_main_menu(),
                )
        else:
            await loading_message.edit_text(
                "❌ Не удалось создать изображение расписания.",
                reply_markup=get_main_menu(),
            )
    else:
        await loading_message.edit_text(
            "❌ Неизвестный тип запроса пользователя.",
            reply_markup=get_main_menu(),
        )


async def handle_schedule_request(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE):
    """Отправляет расписание на текущий выбранный месяц."""
    user_id = update.effective_user.id
    users = load_users_map()
    user_info = users.get(str(user_id))
    if not user_info or not user_info.get("name"):
        await update.message.reply_text(
            "❌ Ваши данные не найдены. Обратитесь к администратору."
        )
        return
    original_employee_name = user_info["name"]
    month = context.user_data.get("selected_month", "ЯНВАРЬ")
    log(
        f"📌 [handle_schedule_request] Запрос расписания для '{original_employee_name}' за {month}, user_id: {user_id}"
    )
    loading_message = await update.message.reply_text("⏳ Загружаю расписание...")
    await context.bot.send_chat_action(chat_id=update.message.chat_id, action="typing")
    try:
        data = pd.read_excel(EXCEL_FILE, sheet_name=month, header=None)
        if data.shape[0] < 2 or data.shape[1] < 3:
            await loading_message.edit_text("❌ Неверная структура данных в Excel.")
            return
    except Exception as e:
        log(
            f"❌ [handle_schedule_request] Ошибка загрузки данных для {month}: {e}")
        await loading_message.edit_text(f"❌ Ошибка загрузки данных: {e}")
        return
    first_row = data.iloc[0].tolist()
    weekdays_row = data.iloc[1].tolist()
    new_columns = first_row[:2] + [str(val) for val in first_row[2:]]
    data.columns = new_columns
    data = data.drop([0, 1]).reset_index(drop=True)
    data["ИМЯ"] = data["ИМЯ"].astype(str).str.strip().str.lower()
    compare_name = original_employee_name.strip().lower()
    employee_data = data[data["ИМЯ"] == compare_name]
    if employee_data.empty:
        await loading_message.edit_text("❌ Нет данных для сотрудника. Проверьте совпадение имени.")
        return
    filename = create_schedule_image(
        data, original_employee_name, month, weekdays_row[2:33])
    if not filename or not os.path.exists(filename):
        await loading_message.edit_text("❌ Не удалось создать изображение расписания.")
        return
    try:
        with open(filename, "rb") as photo:
            await update.message.reply_photo(photo=photo)
        await loading_message.delete()
    except Exception as e:
        log(f"❌ [handle_schedule_request] Ошибка отправки изображения: {e}")
        await loading_message.edit_text(f"❌ Ошибка отправки расписания: {e}")
