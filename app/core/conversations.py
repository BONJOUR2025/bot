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
    PAYMENT_REQUEST_PATTERN,
)
from ..config import ADMIN_ID
from ..handlers.user import (
    home_handler_user,
    view_salary_user,
    view_schedule_user,
    personal_cabinet,
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


def invalid_data_type(update, context):
    """Сообщает пользователю о неверном выборе в меню администратора."""
    from ..keyboards.reply_admin import get_admin_menu

    return update.message.reply_text(
        "Пожалуйста, выберите из предложенных вариантов.",
        reply_markup=get_admin_menu(),
    )




def build_admin_conversation():
    return ConversationHandler(
        entry_points=[
            CommandHandler("admin", admin),
            MessageHandler(filters.Regex("📄 Просмотр данных"), view_data),
            MessageHandler(filters.Regex("💸 Просмотр выплат"), view_payouts),
            MessageHandler(filters.Regex("📢 Рассылка"), handle_broadcast_start),
            MessageHandler(filters.Regex("🔄 Сбросить запросы"), reset_payout_request),
            MessageHandler(filters.Regex("📈 Отчёт по авансам"), report_start),
            MessageHandler(filters.Regex("🏠 Домой"), home_callback),
        ],
        states={
            UserStates.SELECT_DATA_TYPE: [
                MessageHandler(filters.Regex("^🏠 Домой$"), home_callback),
                MessageHandler(filters.Regex("^📅 Расписание$"), select_data_type),
                MessageHandler(filters.Regex("^💰 Зарплаты$"), select_data_type),
                MessageHandler(filters.Regex("^📈 Отчёт по авансам$"), report_start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, invalid_data_type),
            ],
            UserStates.SELECT_MONTH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_month)
            ],
            UserStates.SELECT_EMPLOYEE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_employee)
            ],
            UserStates.SELECT_PAYOUT_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_payout_type)
            ],
            UserStates.SELECT_PERIOD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_period)
            ],
            UserStates.SELECT_STATUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_status)
            ],
            UserStates.SELECT_SORT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_sort)
            ],
            UserStates.SHOW_PAYOUTS: [
                MessageHandler(
                    filters.Regex("⬅️ Назад|➡️ Далее|🏠 Домой"), handle_pagination
                )
            ],
            UserStates.SELECT_EMPLOYEE_FILTER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_employee_filter)
            ],
            AdvanceReportStates.ENTER_START_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_start_date)
            ],
            AdvanceReportStates.ENTER_END_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_end_date)
            ],
            AdvanceReportStates.SELECT_STATUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, report_select_status)
            ],
            UserStates.BROADCAST_MESSAGE: [
                MessageHandler(filters.Regex("^🏠 Домой$"), home_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast_message),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex(r"^(🏠 Домой|Назад|Отмена)$"), global_reset),
            CommandHandler("cancel", cancel_payouts),
        ],
        per_message=True,
    )


def build_manual_payout_conversation():
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^➕ Создать запрос$"), manual_payout_start)
        ],
        states={
            ManualPayoutStates.SELECT_EMPLOYEE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_payout_employee)
            ],
            ManualPayoutStates.SELECT_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_payout_type)
            ],
            ManualPayoutStates.ENTER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_payout_amount)
            ],
            ManualPayoutStates.SELECT_METHOD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_payout_method)
            ],
            ManualPayoutStates.CONFIRM: [
                CallbackQueryHandler(manual_payout_finalize, pattern="^manual_")
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex(r"^(🏠 Домой|Назад|Отмена)$"), global_reset)
        ],
        per_message=True,
    )


def build_payout_conversation():
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(PAYMENT_REQUEST_PATTERN), request_payout_start)
        ],
        states={
            PayoutStates.SELECT_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_type)
            ],
            PayoutStates.ENTER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_amount)
            ],
            PayoutStates.SELECT_METHOD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_method)
            ],
            PayoutStates.CONFIRM_CARD: [
                CallbackQueryHandler(confirm_card, pattern="^payout_")
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex(r"^(🏠 Домой|Назад|Отмена)$"), global_reset)
        ],
        per_message=True,
    )


__all__ = [
    "build_admin_conversation",
    "build_manual_payout_conversation",
    "build_payout_conversation",
]
