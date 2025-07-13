from telegram.ext import (
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from . import (
    menu,
    payout_actions,
    data_view,
    payout_view,
    broadcast,
    manual_payout,
    advance_report,
)
from .menu import *  # noqa: F401,F403
from .payout_actions import *  # noqa: F401,F403
from .data_view import *  # noqa: F401,F403
from .payout_view import *  # noqa: F401,F403
from .broadcast import *  # noqa: F401,F403
from .manual_payout import *  # noqa: F401,F403
from .advance_report import *  # noqa: F401,F403
from ...constants import UserStates, ManualPayoutStates, AdvanceReportStates

__all__ = [name for name in globals() if not name.startswith("_")]


def register_admin_handlers(application):
    # Главное меню администратора
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^🏠 Домой$"), menu.home_callback))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📄 Просмотр данных$"), data_view.view_data))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📢 Рассылка$"), broadcast.handle_broadcast_start))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^💸 Просмотр выплат$"), payout_view.view_payouts))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📈 Отчёт по авансам$"), advance_report.report_start))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^➕ Создать запрос$"), manual_payout.manual_payout_start))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^🔄 Сбросить запросы$"), payout_actions.reset_payout_request))

    # FSM: Отчёт по авансам
    application.add_handler(
        ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^📈 Отчёт по авансам$"), advance_report.report_start)],
            states={
                AdvanceReportStates.ENTER_START_DATE: [MessageHandler(filters.TEXT, advance_report.enter_start_date)],
                AdvanceReportStates.ENTER_END_DATE: [MessageHandler(filters.TEXT, advance_report.enter_end_date)],
                AdvanceReportStates.SELECT_STATUS: [MessageHandler(filters.TEXT, advance_report.report_select_status)],
            },
            fallbacks=[MessageHandler(filters.Regex("🏠 Домой"), menu.home_callback)],
            name="advance_report",
            persistent=False,
        )
    )

    # FSM: Ручной запрос на выплату
    application.add_handler(
        ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^➕ Создать запрос$"), manual_payout.manual_payout_start)],
            states={
                ManualPayoutStates.SELECT_EMPLOYEE: [MessageHandler(filters.TEXT, manual_payout.manual_payout_employee)],
                ManualPayoutStates.SELECT_TYPE: [MessageHandler(filters.TEXT, manual_payout.manual_payout_type)],
                ManualPayoutStates.ENTER_AMOUNT: [MessageHandler(filters.TEXT, manual_payout.manual_payout_amount)],
                ManualPayoutStates.SELECT_METHOD: [MessageHandler(filters.TEXT, manual_payout.manual_payout_method)],
                ManualPayoutStates.CONFIRM: [CallbackQueryHandler(manual_payout.manual_payout_finalize, pattern="^manual_")],
            },
            fallbacks=[MessageHandler(filters.Regex("🏠 Домой"), menu.home_callback)],
            name="manual_payout",
            persistent=False,
        )
    )

    # FSM: Просмотр выплат (фильтры, пагинация)
    application.add_handler(
        ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^💸 Просмотр выплат$"), payout_view.view_payouts)],
            states={
                UserStates.SELECT_PAYOUT_TYPE: [MessageHandler(filters.TEXT, payout_view.select_payout_type)],
                UserStates.SELECT_PERIOD: [MessageHandler(filters.TEXT, payout_view.select_period)],
                UserStates.SELECT_STATUS: [MessageHandler(filters.TEXT, payout_view.select_status)],
                UserStates.SELECT_EMPLOYEE_FILTER: [MessageHandler(filters.TEXT, payout_view.select_employee_filter)],
                UserStates.SELECT_SORT: [MessageHandler(filters.TEXT, payout_view.select_sort)],
                UserStates.SHOW_PAYOUTS: [MessageHandler(filters.TEXT, payout_view.handle_pagination)],
            },
            fallbacks=[MessageHandler(filters.Regex("🏠 Домой"), menu.home_callback)],
            name="view_payouts",
            persistent=False,
        )
    )

    # FSM: Просмотр данных (зарплаты / расписание)
    application.add_handler(
        ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^📄 Просмотр данных$"), data_view.view_data)],
            states={
                UserStates.SELECT_DATA_TYPE: [MessageHandler(filters.TEXT, data_view.select_data_type)],
                UserStates.SELECT_MONTH: [MessageHandler(filters.TEXT, data_view.select_month)],
                UserStates.SELECT_EMPLOYEE: [MessageHandler(filters.TEXT, data_view.select_employee)],
            },
            fallbacks=[MessageHandler(filters.Regex("🏠 Домой"), menu.home_callback)],
            name="view_data",
            persistent=False,
        )
    )

    # FSM: Рассылка
    application.add_handler(
        ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^📢 Рассылка$"), broadcast.handle_broadcast_start)],
            states={
                UserStates.BROADCAST_MESSAGE: [MessageHandler(filters.TEXT, broadcast.handle_broadcast_message)],
                UserStates.BROADCAST_CONFIRM: [CallbackQueryHandler(broadcast.handle_broadcast_confirm)],
            },
            fallbacks=[MessageHandler(filters.Regex("🏠 Домой"), menu.home_callback)],
            name="broadcast",
            persistent=False,
        )
    )

    # Инлайн-кнопки одобрения/отмены
    application.add_handler(CallbackQueryHandler(payout_actions.allow_payout, pattern="^allow_"))
    application.add_handler(CallbackQueryHandler(payout_actions.deny_payout, pattern="^deny_"))
    application.add_handler(CallbackQueryHandler(payout_actions.mark_sent, pattern="^mark_sent_"))
