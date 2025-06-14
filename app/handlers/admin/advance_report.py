import datetime
from telegram import (
    Update,
    ReplyKeyboardRemove,
    InputFile,
    ReplyKeyboardMarkup,
)
from telegram.ext import ContextTypes, ConversationHandler

from ...constants import AdvanceReportStates
from ...config import ADMIN_ID
from ...keyboards.reply_admin import get_admin_menu
from ...services.advance_report import (
    generate_advance_report,
    save_markdown_file,
)


async def report_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return ConversationHandler.END
    await update.message.reply_text(
        "Введите начальную дату в формате YYYY-MM-DD:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return AdvanceReportStates.ENTER_START_DATE


async def enter_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        start_date = datetime.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат. Используйте YYYY-MM-DD."
        )
        return AdvanceReportStates.ENTER_START_DATE
    context.user_data["report_start_date"] = start_date
    await update.message.reply_text(
        "Введите конечную дату в формате YYYY-MM-DD:"
    )
    return AdvanceReportStates.ENTER_END_DATE


async def enter_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        end_date = datetime.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат. Используйте YYYY-MM-DD."
        )
        return AdvanceReportStates.ENTER_END_DATE
    start_date = context.user_data.get("report_start_date")
    if not start_date:
        await update.message.reply_text("❌ Начальная дата не указана.")
        return ConversationHandler.END
    if end_date < start_date:
        await update.message.reply_text(
            "❌ Конечная дата раньше начальной. Повторите ввод."
        )
        return AdvanceReportStates.ENTER_END_DATE

    context.user_data["report_end_date"] = end_date
    keyboard = [
        ["Ожидает", "Одобрено"],
        ["Отклонено", "Отменено"],
        ["Все статусы"],
    ]
    await update.message.reply_text(
        "Выберите статусы для отчёта:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard, resize_keyboard=True, one_time_keyboard=True
        ),
    )
    return AdvanceReportStates.SELECT_STATUS


async def select_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = update.message.text.strip()
    valid = {"Ожидает", "Одобрено", "Отклонено", "Отменено", "Все статусы"}
    if status not in valid:
        await update.message.reply_text("❌ Выберите вариант из списка.")
        return AdvanceReportStates.SELECT_STATUS

    statuses = None if status == "Все статусы" else [status]
    start_date = context.user_data.get("report_start_date")
    end_date = context.user_data.get("report_end_date")

    df = generate_advance_report(start_date, end_date, statuses)
    if df.empty:
        await update.message.reply_text(
            "Нет данных по авансам за указанный период.",
            reply_markup=get_admin_menu(),
        )
        return ConversationHandler.END

    filename = save_markdown_file(df)
    with open(filename, "rb") as f:
        await update.message.reply_document(
            document=InputFile(f, filename=filename)
        )

    await update.message.reply_text(
        "🏠 Возврат в меню администратора.", reply_markup=get_admin_menu()
    )
    return ConversationHandler.END


# Export under an alias to avoid name conflicts with payout status handler
report_select_status = select_status
