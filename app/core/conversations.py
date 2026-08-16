from telegram.ext import (
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from ..constants import (
    UserStates,
    AdvanceReportStates,
    ManualPayoutStates,
    PayoutStates,
    ShiftCheckinStates,
    PAYMENT_REQUEST_PATTERN,
)
from ..config import ADMIN_ID
from ..handlers.user import (
    home_handler_user,
    view_salary_user,
    view_schedule_user,
    personal_cabinet,
    open_salon_start,
    open_salon_photo,
    open_salon_cancel,
)
from ..handlers.user.payout import (
    request_payout_start,
    select_type,
    enter_amount,
    select_method,
    confirm_card,
)
from ..handlers.admin import (
    admin,
    view_data,
    select_data_type,
    select_month,
    select_employee,
    allow_payout,
    deny_payout,
    home_callback,
    reset_payout_request,
    view_payouts,
    select_payout_type,
    select_period,
    select_status,
    select_employee_filter,
    select_sort,
    handle_pagination,
    cancel_payouts,
    show_payouts_page,
    handle_broadcast_start,
    handle_broadcast_message,
    handle_broadcast_confirm,
    handle_broadcast_send,
    manual_payout_start,
    manual_payout_employee,
    manual_payout_type,
    manual_payout_amount,
    manual_payout_method,
    manual_payout_finalize,
    report_start,
    enter_start_date,
    enter_end_date,
    report_select_status,
)
from ..handlers.reset import global_reset
from ..handlers.user.start import start as start_handler
from .resilience import entry, step, steps


async def reset_and_start(update, context):
    """Reset all conversation states and return to start menu."""
    # Clear conversation states for this user
    app = context.application
    for handler, conversations in app._conversation_handler_conversations.items():
        key = handler._get_key(update)
        if key in conversations:
            conversations.pop(key)
    context.user_data.clear()
    # Return to start
    return await start_handler(update, context)


def invalid_data_type(update, context):
    """Сообщает пользователю о неверном выборе в меню администратора."""
    from ..keyboards.reply_admin import get_admin_menu

    return update.message.reply_text(
        "Пожалуйста, выберите из предложенных вариантов.",
        reply_markup=get_admin_menu(),
    )




def build_admin_conversation():
    admin_filter = filters.User(ADMIN_ID)
    return ConversationHandler(
        entry_points=[
            CommandHandler("admin", entry(admin, UserStates.SELECT_DATA_TYPE), filters=admin_filter),
            MessageHandler(filters.Regex("📄 Просмотр данных") & admin_filter,
                           entry(view_data, UserStates.SELECT_DATA_TYPE)),
            MessageHandler(filters.Regex("💸 Просмотр выплат") & admin_filter,
                           entry(view_payouts, UserStates.SELECT_PAYOUT_TYPE)),
            MessageHandler(filters.Regex("📢 Рассылка") & admin_filter,
                           entry(handle_broadcast_start, UserStates.BROADCAST_MESSAGE)),
            # Сброс и «Домой» ничего не открывают — им хватает step().
            MessageHandler(filters.Regex("🔄 Сбросить запросы") & admin_filter,
                           step(reset_payout_request)),
            MessageHandler(filters.Regex("📈 Отчёт по авансам") & admin_filter,
                           entry(report_start, AdvanceReportStates.ENTER_START_DATE)),
            MessageHandler(filters.Regex("🏠 Домой") & admin_filter, step(home_callback)),
        ],
        states={
            UserStates.SELECT_DATA_TYPE: [
                MessageHandler(filters.Regex("^🏠 Домой$"), step(home_callback)),
                MessageHandler(filters.Regex("^📅 Расписание$"), step(select_data_type)),
                MessageHandler(filters.Regex("^💰 Зарплаты$"), step(select_data_type)),
                MessageHandler(filters.Regex("^📈 Отчёт по авансам$"), step(report_start)),
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(invalid_data_type)),
            ],
            UserStates.SELECT_MONTH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(select_month))
            ],
            UserStates.SELECT_EMPLOYEE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(select_employee))
            ],
            UserStates.SELECT_PAYOUT_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(select_payout_type))
            ],
            UserStates.SELECT_PERIOD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(select_period))
            ],
            UserStates.SELECT_STATUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(select_status))
            ],
            UserStates.SELECT_SORT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(select_sort))
            ],
            UserStates.SHOW_PAYOUTS: [
                MessageHandler(
                    filters.Regex("⬅️ Назад|➡️ Далее|🏠 Домой"), step(handle_pagination)
                )
            ],
            UserStates.SELECT_EMPLOYEE_FILTER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(select_employee_filter))
            ],
            AdvanceReportStates.ENTER_START_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(enter_start_date))
            ],
            AdvanceReportStates.ENTER_END_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(enter_end_date))
            ],
            AdvanceReportStates.SELECT_STATUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(report_select_status))
            ],
            UserStates.BROADCAST_MESSAGE: [
                MessageHandler(filters.Regex("^🏠 Домой$"), step(home_callback)),
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(handle_broadcast_message)),
            ],
            UserStates.BROADCAST_CONFIRM: [
                CallbackQueryHandler(step(handle_broadcast_confirm)),
            ],
        },
        fallbacks=[
            CommandHandler("start", step(reset_and_start)),
            MessageHandler(filters.Regex(r"^(🏠 Домой|Назад|Отмена)$"), step(global_reset)),
            CommandHandler("cancel", step(cancel_payouts)),
        ],
        per_chat=True,
    )


def build_manual_payout_conversation():
    admin_filter = filters.User(ADMIN_ID)
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^➕ Создать запрос$") & admin_filter,
                           entry(manual_payout_start, ManualPayoutStates.SELECT_EMPLOYEE))
        ],
        states={
            ManualPayoutStates.SELECT_EMPLOYEE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(manual_payout_employee))
            ],
            ManualPayoutStates.SELECT_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(manual_payout_type))
            ],
            ManualPayoutStates.ENTER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(manual_payout_amount))
            ],
            ManualPayoutStates.SELECT_METHOD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(manual_payout_method))
            ],
            ManualPayoutStates.CONFIRM: [
                CallbackQueryHandler(step(manual_payout_finalize), pattern="^manual_")
            ],
        },
        fallbacks=[
            CommandHandler("start", step(reset_and_start)),
            MessageHandler(filters.Regex(r"^(🏠 Домой|Назад|Отмена)$"), step(global_reset)),
        ],
        per_chat=True,
    )


def build_payout_conversation():
    # Pattern for main menu buttons that should exit payout flow
    menu_buttons = filters.Regex(
        r"^(📄 Просмотр ЗП|📅 Просмотр расписания|👤 Личный кабинет)$"
    )
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(PAYMENT_REQUEST_PATTERN),
                           entry(request_payout_start, PayoutStates.SELECT_TYPE))
        ],
        states={
            PayoutStates.SELECT_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(select_type))
            ],
            PayoutStates.ENTER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(enter_amount))
            ],
            PayoutStates.SELECT_METHOD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step(select_method))
            ],
            PayoutStates.CONFIRM_CARD: [
                CallbackQueryHandler(step(confirm_card), pattern="^payout_")
            ],
        },
        fallbacks=[
            CommandHandler("start", step(reset_and_start)),
            MessageHandler(filters.Regex(r"^(🏠 Домой|Назад|Отмена|❌ Отмена|🔙 Назад)$"), step(global_reset)),
            # Allow re-entering the payout flow
            MessageHandler(filters.Regex(PAYMENT_REQUEST_PATTERN),
                           entry(request_payout_start, PayoutStates.SELECT_TYPE)),
            # Exit to menu items
            MessageHandler(menu_buttons, step(global_reset)),
        ],
        per_chat=True,
    )


def build_shift_checkin_conversation():
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^🏪 Открыть салон$"),
                           entry(open_salon_start, ShiftCheckinStates.AWAITING_PHOTO))
        ],
        states={
            ShiftCheckinStates.AWAITING_PHOTO: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, step(open_salon_photo)),
                MessageHandler(filters.Regex(r"^🏠 Домой$"), step(open_salon_cancel)),
            ],
        },
        fallbacks=[
            CommandHandler("start", step(reset_and_start)),
            MessageHandler(filters.Regex(r"^(🏠 Домой|Назад|Отмена|❌ Отмена|🔙 Назад)$"), step(open_salon_cancel)),
        ],
        per_chat=True,
    )


__all__ = [
    "build_admin_conversation",
    "build_manual_payout_conversation",
    "build_payout_conversation",
    "build_shift_checkin_conversation",
]
