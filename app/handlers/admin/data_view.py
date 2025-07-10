import os
import pandas as pd
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from ...constants import UserStates
from ...config import EXCEL_FILE
from ...services.users import load_users_map
from ...keyboards.reply_admin import get_admin_menu, get_month_keyboard, get_home_button
from ...services.excel import load_data
from ...services.report import generate_employee_report
from ...utils.image import create_combined_table_image, create_schedule_image
from ...utils.logger import log


async def view_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = context.application.chat_data.get(chat_id, {}).get("conversation")
    log(f"[FSM] state before entry: {state}")
    keyboard = [["📅 Расписание", "💰 Зарплаты"], ["🏠 Домой"]]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=False
    )
    await update.message.reply_text(
        "📊 Что хотите посмотреть?", reply_markup=reply_markup
    )
    context.user_data["viewing_data"] = True
    return UserStates.SELECT_DATA_TYPE


async def select_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    month = update.message.text
    log(f"🚀 [select_month] Выбран месяц: {month}")
    context.user_data["selected_month"] = month
    employees = get_employee_list(EXCEL_FILE, month)
    if not employees:
        await update.message.reply_text(
            f"❌ Нет данных за {month}.", reply_markup=get_admin_menu()
        )
        return UserStates.SELECT_DATA_TYPE
    await update.message.reply_text(
        f"Выберите сотрудника для {month}:",
        reply_markup=get_employees_keyboard(employees),
    )
    context.user_data["awaiting_employee"] = True
    return UserStates.SELECT_EMPLOYEE


async def select_data_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log("📥 [select_data_type] Функция вызвана")
    data_type = update.message.text
    log(f"🚀 [select_data_type] Выбрано: '{data_type}'")

    if data_type == "💰 Зарплаты":
        context.user_data["data_type"] = "salary"
        await update.message.reply_text(
            "Выберите месяц:", reply_markup=get_month_keyboard()
        )
        return UserStates.SELECT_MONTH
    elif data_type == "📅 Расписание":
        context.user_data["data_type"] = "schedule"
        await update.message.reply_text(
            "Выберите месяц:", reply_markup=get_month_keyboard()
        )
        return UserStates.SELECT_MONTH
    else:
        await update.message.reply_text(
            "Пожалуйста, выберите из предложенных вариантов.",
            reply_markup=get_admin_menu(),
        )
        return UserStates.SELECT_DATA_TYPE


async def select_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    employee_name = update.message.text
    month = context.user_data.get("selected_month")
    data_type = context.user_data.get("data_type")
    log(
        f"DEBUG [select_employee] Выбран сотрудник: '{employee_name}', месяц: {month}, data_type: '{data_type}'"
    )
    context.user_data["selected_employee"] = employee_name
    context.user_data["awaiting_employee"] = False
    if data_type == "salary":
        await handle_salary_admin(update, context)
    elif data_type == "schedule":
        await handle_schedule_admin(update, context)
    else:
        await update.message.reply_text(
            "❌ Неизвестный тип данных.", reply_markup=get_admin_menu()
        )
    return UserStates.SELECT_DATA_TYPE


async def handle_salary_admin(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE):
    month = context.user_data.get("selected_month")
    employee_name = context.user_data.get("selected_employee")
    if not month or not employee_name:
        await update.message.reply_text(
            "❌ Не выбраны месяц или сотрудник.", reply_markup=get_admin_menu()
        )
        return
    employee_name = update.message.text.strip()
    user_id = str(update.effective_user.id)
    log(
        f"📌 [handle_salary_admin] Пользователь {user_id} запросил зарплату для '{employee_name}' за {month}"
    )
    loading_message = await update.message.reply_text(
        "⏳ Загружаю данные о зарплате..."
    )
    await context.bot.send_chat_action(
        chat_id=update.message.chat_id, action="typing"
    )
    try:
        data = load_data(sheet_name=month)
        if data is None:
            log(f"❌ [handle_salary_admin] Данные для {month} не найдены.")
            await loading_message.edit_text(
                f"❌ Ошибка: данные за {month} не найдены."
            )
            return
        if "ИМЯ" not in data.columns:
            log(
                f"❌ [handle_salary_admin] Столбец 'ИМЯ' отсутствует в данных за {month}")
            await loading_message.edit_text(
                f"❌ Ошибка: неверная структура данных для {month}."
            )
            return
        log(f"✅ [handle_salary_admin] Данные загружены: {list(data.columns)}")
    except Exception as e:
        log(f"❌ [handle_salary_admin] Ошибка загрузки данных: {e}")
        await loading_message.edit_text(f"❌ Ошибка загрузки данных: {e}")
        return
    data["ИМЯ"] = data["ИМЯ"].astype(str).str.strip()
    employee_data = data[data["ИМЯ"] == employee_name]
    if employee_data.empty:
        log(
            f"❌ [handle_salary_admin] Сотрудник '{employee_name}' не найден в данных за {month}"
        )
        await loading_message.edit_text(
            f"❌ Сотрудник {employee_name} не найден за {month}."
        )
        return
    row_index = employee_data.index[0]
    log(
        f"✅ [handle_salary_admin] Найден сотрудник '{employee_name}' на строке {row_index}"
    )
    try:
        report_tables = generate_employee_report(
            employee_name, month, data, row_index
        )
        if not report_tables:
            log(
                f"❌ [handle_salary_admin] Отчёт не сгенерирован для {employee_name}")
            await loading_message.edit_text(
                "❌ Ошибка: отчёт не сгенерирован."
            )
            return
        log(
            f"✅ [handle_salary_admin] Отчёт сгенерирован, таблиц: {len(report_tables)}"
        )
    except Exception as e:
        log(f"❌ [handle_salary_admin] Ошибка генерации отчёта: {e}")
        await loading_message.edit_text(f"❌ Ошибка генерации отчёта: {e}")
        return
    filename = create_combined_table_image(
        report_tables, f"salary_report_admin_{user_id}.png"
    )
    if not filename or not os.path.exists(filename):
        log(f"❌ [handle_salary_admin] Файл изображения не создан: {filename}")
        await loading_message.edit_text(
            "❌ Не удалось создать изображение отчёта."
        )
        return
    log(f"✅ [handle_salary_admin] Файл изображения создан: {filename}")
    try:
        with open(filename, "rb") as photo:
            await update.message.reply_photo(photo=photo)
        log(
            f"✅ [handle_salary_admin] Изображение отправлено пользоателю {user_id}")
        try:
            await loading_message.delete()
        except Exception as e:
            log(f"⚠️ [handle_salary_admin] Ошибка удаления сообщения: {e}")
        await update.message.reply_text(
            "🏠 Возврат в главное меню...", reply_markup=get_admin_menu()
        )
        return ConversationHandler.END
    except Exception as e:
        log(f"❌ [handle_salary_admin] Ошибка отправки изображения: {e}")
        await loading_message.edit_text(f"❌ Ошибка отправки отчёта: {e}")


async def handle_schedule_admin(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    employee_name = context.user_data.get("selected_employee")
    month = context.user_data.get("selected_month")
    if not employee_name or not month:
        await update.message.reply_text(
            "❌ Не выбраны сотрудник или месяц.", reply_markup=get_admin_menu()
        )
        return UserStates.SELECT_DATA_TYPE
    loading_message = await update.message.reply_text(
        "⏳ Загружаю расписание..."
    )
    await context.bot.send_chat_action(
        chat_id=update.message.chat_id, action="typing"
    )
    try:
        data = pd.read_excel(EXCEL_FILE, sheet_name=month, header=None)
        if data.shape[0] < 2 or data.shape[1] < 3:
            log(
                f"❌ [handle_schedule_admin] Неверная структура данных для {month}: {data.shape}"
            )
            await loading_message.edit_text(
                "❌ Неверная структура данных в Excel."
            )
            return UserStates.SELECT_DATA_TYPE
        log(
            f"✅ [handle_schedule_admin] Данные загружены, размер: {data.shape}"
        )
    except Exception as e:
        log(
            f"❌ [handle_schedule_admin] Ошибка загрузки данных для {month}: {e}")
        await loading_message.edit_text(f"❌ Ошибка загрузки данных: {e}")
        return UserStates.SELECT_DATA_TYPE
    first_row = data.iloc[0].tolist()
    weekdays_row = data.iloc[1].tolist()
    new_columns = first_row[:2] + [str(val) for val in first_row[2:]]
    data.columns = new_columns
    data = data.drop([0, 1]).reset_index(drop=True)
    data["ИМЯ"] = data["ИМЯ"].astype(str).str.strip().str.lower()
    compare_name = employee_name.strip().lower()
    log(
        f"DEBUG [handle_schedule_admin] Столбцы: {data.columns.tolist()}, Имя для поиска: '{compare_name}'"
    )
    log(f"DEBUG [handle_schedule_admin] Дни недели: {weekdays_row[2:33]}")
    employee_data = data[data["ИМЯ"] == compare_name]
    if employee_data.empty:
        log(
            f"❌ [handle_schedule_admin] Сотрудник '{employee_name}' не найден в данных за {month}"
        )
        await loading_message.edit_text(
            "❌ Нет данных для сотрудника. Проверьте совпадение имени."
        )
        return
    log(f"✅ [handle_schedule_admin] Сотрудник '{employee_name}' найден.")
    filename = create_schedule_image(
        data, employee_name, month, weekdays_row[2:33]
    )
    log(
        f"DEBUG [handle_schedule_admin] Результат create_schedule_image: {filename}"
    )
    if not filename or not os.path.exists(filename):
        log(
            f"❌ [handle_schedule_admin] Файл изображения не создан: {filename}"
        )
        await loading_message.edit_text(
            "❌ Не удалось создать изображение расписания."
        )
        return UserStates.SELECT_DATA_TYPE
    log(f"✅ [handle_schedule_admin] Файл изображения создан: {filename}")
    try:
        with open(filename, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption="Расписание отправлено. Что дальше?",
                reply_markup=get_home_button(),
            )
        log(
            f"✅ [handle_schedule_admin] Расписание отправлено пользователю {user_id}")
        await loading_message.delete()
    except Exception as e:
        log(f"❌ [handle_schedule_admin] Ошибка отправки изображения: {e}")
        await loading_message.edit_text(f"❌ Ошибка отправки расписания: {e}")
        return UserStates.SELECT_DATA_TYPE
    return UserStates.SELECT_DATA_TYPE


def get_employee_list(excel_file, sheet_name):
    data = load_data(sheet_name)
    if data is None or "ИМЯ" not in data.columns:
        return []
    return data["ИМЯ"].dropna().unique().tolist()


def get_employees_keyboard(employees):
    keyboard = [[emp] for emp in employees] + [["🏠 Домой"]]
    return ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=False
    )
