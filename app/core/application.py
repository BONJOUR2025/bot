from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from ..config import TOKEN, ADMIN_ID
from ..utils.logger import log
from ..handlers.callback_logger import log_button_press
from .conversations import (
    build_admin_conversation,
    build_manual_payout_conversation,
    build_payout_conversation,
)
from ..handlers.user import (
    handle_salary_request,
    start,
    home_handler_user,
    handle_selected_month_user,
    view_salary_user,
    view_schedule_user,
    personal_cabinet,
    view_user_info,
    edit_user_info,
    handle_edit_selection,
    save_new_value,
    view_request_history,
    handle_edit_confirmation,
    handle_admin_change_response,
    handle_acknowledgment,
)
from ..handlers.admin import (
    admin,
    view_data,
    allow_payout,
    deny_payout,
    home_callback,
    exit_admin,
    handle_salary_admin,
    handle_schedule_admin,
    reset_payout_request,
    mark_sent,
    view_payouts,
    show_employee_keyboard,
    handle_pagination,
    cancel_payouts,
    show_payouts_page,
    handle_broadcast_start,
    handle_broadcast_message,
    handle_broadcast_confirm,
    handle_broadcast_send,
)
from ..handlers.reset import global_reset
import datetime


def create_application():
    app = ApplicationBuilder().token(TOKEN).build()
    register_all_handlers(app)
    register_jobs(app)

    return app


def _register_all_handlers(app):
    admin_conv_handler = build_admin_conversation()
    manual_payout_handler = build_manual_payout_conversation()
    payout_conv_handler = build_payout_conversation()
    reset_filter = filters.Regex(r"^(🏠 Домой|🔙 Назад|❌ Отмена)$")
    # Log all callback button presses before other handlers process them
    app.add_handler(
        CallbackQueryHandler(log_button_press, block=False),
        group=-1,
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        CommandHandler("salary", handle_salary_request, filters=~filters.User(ADMIN_ID))
    )
    app.add_handler(
        CommandHandler(
            "schedule", handle_salary_request, filters=~filters.User(ADMIN_ID)
        )
    )
    app.add_handler(admin_conv_handler)
    app.add_handler(manual_payout_handler)
    app.add_handler(payout_conv_handler)
    app.add_handler(CallbackQueryHandler(allow_payout, pattern=r"^allow_payout_"))
    app.add_handler(CallbackQueryHandler(deny_payout, pattern=r"^deny_payout_"))
    app.add_handler(
        CallbackQueryHandler(
            handle_edit_confirmation, pattern=r"^(confirm_|cancel_edit)"
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            handle_admin_change_response, pattern=r"^(approve_change_|reject_change_)"
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^📄 Просмотр ЗП$") & ~filters.User(ADMIN_ID),
            view_salary_user,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^📅 Просмотр расписания$") & ~filters.User(ADMIN_ID),
            view_schedule_user,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Regex(
                r"^(ЯНВАРЬ|ФЕВРАЛЬ|МАРТ|АПРЕЛЬ|МАЙ|ИЮНЬ|ИЮЛЬ|АВГУСТ|СЕНТЯБРЬ|ОКТЯБРЬ|НОЯБРЬ|ДЕКАБРЬ)$"
            )
            & ~filters.User(ADMIN_ID),
            handle_selected_month_user,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^👤 Личный кабинет$") & ~filters.User(ADMIN_ID),
            personal_cabinet,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^📋 Мои данные$") & ~filters.User(ADMIN_ID), view_user_info
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^✏️ Изменить данные$") & ~filters.User(ADMIN_ID),
            edit_user_info,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^(📱 Изменить телефон|🏦 Изменить банк)$")
            & ~filters.User(ADMIN_ID),
            handle_edit_selection,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^📜 История запросов$") & ~filters.User(ADMIN_ID),
            view_request_history,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^🏠 Домой$") & ~filters.User(ADMIN_ID), home_handler_user
        )
    )
    app.add_handler(
        CommandHandler(
            "reset_payout", reset_payout_request, filters=filters.User(ADMIN_ID)
        )
    )
    app.add_handler(MessageHandler(reset_filter, global_reset), group=0)
    app.add_handler(CommandHandler("cancel", global_reset), group=0)
    app.add_handler(CallbackQueryHandler(mark_sent, pattern=r"^mark_sent_"))
    app.add_handler(CallbackQueryHandler(handle_acknowledgment, pattern=r"^ack_"))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.User(ADMIN_ID), save_new_value
        )
    )
    app.add_error_handler(error_handler)


def register_admin_handlers(app):
    """Register admin-specific handlers."""
    _register_all_handlers(app)


def register_user_handlers(app):
    """Register user handlers (currently included in admin registration)."""


def register_fallbacks(app):
    """Register fallback handlers (currently included in admin registration)."""


def register_all_handlers(app):
    register_admin_handlers(app)
    register_user_handlers(app)
    register_fallbacks(app)


async def error_handler(update, context):
    from telegram.error import BadRequest

    err = context.error
    if isinstance(err, BadRequest) and "Inline keyboard expected" in str(err):
        # Игнорируем ошибку, возникающую при повторном нажатии по удалённой
        # кнопке
        log(f"⚠️ [error_handler] Игнорируем ошибку: {err}")
        return
    log(f"❌ [error_handler] Произошла ошибка: {err}")
    if update and update.message and not context.user_data.get("request_sent", False):
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")


def register_jobs(app):
    from datetime import time
    from telegram.ext import ContextTypes
    from ..config import ADMIN_CHAT_ID
    from ..services.birthday_service import get_upcoming_birthdays

    async def birthday_reminder(context: ContextTypes.DEFAULT_TYPE):
        today = datetime.date.today()
        upcoming = get_upcoming_birthdays(1)
        today_lines = []
        tomorrow_lines = []
        for b in upcoming:
            bdate = datetime.date.fromisoformat(b["birthdate"])
            d_this = datetime.date(today.year, bdate.month, bdate.day)
            diff = (d_this - today).days
            line = f"- {b['full_name']} ({bdate.strftime('%d.%m')})"
            if diff == 0:
                today_lines.append(line)
            elif diff == 1:
                tomorrow_lines.append(line)
        messages = []
        if today_lines:
            messages.append("🎉 Сегодня день рождения у:\n" + "\n".join(today_lines))
        if tomorrow_lines:
            messages.append("ℹ️ Завтра день рождения у:\n" + "\n".join(tomorrow_lines))
        if messages and ADMIN_CHAT_ID:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID, text="\n\n".join(messages)
            )

    app.job_queue.run_daily(birthday_reminder, time(hour=9, minute=0))
