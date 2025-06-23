from telegram.ext import (
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from ..constants import (
    UserStates,
    PayoutStates,
    AdvanceReportStates,
    ManualPayoutStates,
)
from ..config import ADMIN_ID
from ..handlers.user import (
    request_payout_user,
    handle_payout_type_user,
    handle_payout_amount_user,
    payout_method_user,
    handle_card_confirmation,
    home_handler_user,
    view_salary_user,
    view_schedule_user,
    personal_cabinet,
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
    show_birthdays,
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


def invalid_data_type(update, context):
    """Сообщает пользователю о неверном выборе в меню администратора."""
    from ..keyboards.reply_admin import get_admin_menu

    return update.message.reply_text(
        "Пожалуйста, выберите из предложенных вариантов.",
        reply_markup=get_admin_menu(),
    )


def build_payout_conversation():
    return ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(r"^💰 Запросить выплату$") & ~filters.User(ADMIN_ID),
                request_payout_user,
            ),
            MessageHandler(
                filters.Regex(r"^📄 Просмотр ЗП$") & ~filters.User(ADMIN_ID),
                view_salary_user,
            ),
            MessageHandler(
                filters.Regex(r"^📅 Просмотр расписания$") & ~filters.User(ADMIN_ID),
                view_schedule_user,
            ),
            MessageHandler(
                filters.Regex(r"^👤 Личный кабинет$") & ~filters.User(ADMIN_ID),
                personal_cabinet,
            ),
            MessageHandler(
                filters.Regex(r"^🏠 Домой$") & ~filters.User(ADMIN_ID),
                home_handler_user,
            ),
        ],
        states={
            PayoutStates.SELECT_TYPE: [
                MessageHandler(
                    filters.Regex(r"^(Аванс|Зарплата|🏠 Домой)$")
                    & ~filters.User(ADMIN_ID),
                    handle_payout_type_user,
                ),
            ],
            PayoutStates.ENTER_AMOUNT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.User(ADMIN_ID),
                    handle_payout_amount_user,
                ),
            ],
            PayoutStates.SELECT_METHOD: [
                MessageHandler(
                    filters.Regex(r"^(🏦 Из кассы|🤝 Наличными|💳 На карту|🏠 Домой)$")
                    & ~filters.User(ADMIN_ID),
                    payout_method_user,
                ),
            ],
            PayoutStates.CONFIRM_CARD: [
                CallbackQueryHandler(
                    handle_card_confirmation, pattern=r"^(confirm_card|cancel_card)$"
                ),
            ],
        },
        fallbacks=[
            MessageHandler(
                filters.Regex(r"^🏠 Домой$") & ~filters.User(ADMIN_ID),
                home_handler_user,
            ),
            MessageHandler(
                filters.Regex(r"^📄 Просмотр ЗП$") & ~filters.User(ADMIN_ID),
                view_salary_user,
            ),
            MessageHandler(
                filters.Regex(r"^📅 Просмотр расписания$") & ~filters.User(ADMIN_ID),
                view_schedule_user,
            ),
            MessageHandler(
                filters.Regex(r"^👤 Личный кабинет$") & ~filters.User(ADMIN_ID),
                personal_cabinet,
            ),
        ],
    )


def build_admin_conversation():
    return ConversationHandler(
        entry_points=[
            CommandHandler("admin", admin),
            MessageHandler(filters.Regex("📄 Просмотр данных"), view_data),
            MessageHandler(filters.Regex("💸 Просмотр выплат"), view_payouts),
            MessageHandler(filters.Regex("📢 Рассылка"), handle_broadcast_start),
            MessageHandler(filters.Regex("🔄 Сбросить запросы"), reset_payout_request),
            MessageHandler(filters.Regex("🎂 Дни рождения"), show_birthdays),
            MessageHandler(filters.Regex("📈 Отчёт по авансам"), report_start),
            MessageHandler(filters.Regex("🏠 Домой"), home_callback),
        ],
        states={
            UserStates.SELECT_DATA_TYPE: [
                MessageHandler(filters.Regex("^🏠 Домой$"), home_callback),
                MessageHandler(filters.Regex("^📅 Расписание$"), select_data_type),
                MessageHandler(filters.Regex("^💰 Зарплаты$"), select_data_type),
                MessageHandler(filters.Regex("^🎂 Дни рождения$"), show_birthdays),
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
            MessageHandler(filters.Regex("🏠 Домой"), home_callback),
            CommandHandler("cancel", cancel_payouts),
        ],
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
        fallbacks=[MessageHandler(filters.Regex("🏠 Домой"), home_callback)],
    )


__all__ = [
    "build_payout_conversation",
    "build_admin_conversation",
    "build_manual_payout_conversation",
]
