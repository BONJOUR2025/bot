

from telegram.ext import (
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from .start import get_user_info_user, start
from .home import home_handler_user
from .menu import (
    view_salary_user,
    view_schedule_user,
    handle_selected_month_user,
    handle_schedule_request,
)
from .cabinet import (
    personal_cabinet,
    view_user_info,
    edit_user_info,
    handle_edit_selection,
    save_new_value,
    view_request_history,
    handle_edit_confirmation,
    handle_admin_change_response,
)
from .salary import handle_salary_request
from .ack import handle_acknowledgment

from app.constants import PayoutStates
from . import payout


def register_user_handlers(application):
    """Register conversation handlers for regular users."""
    application.add_handler(
        ConversationHandler(
            entry_points=[
                MessageHandler(
                    filters.TEXT & filters.Regex(r"💰 Запросить выплату"),
                    payout.request_payout_start,
                ),
            ],
            states={
                PayoutStates.SELECT_TYPE: [
                    MessageHandler(
                        filters.TEXT & (~filters.COMMAND),
                        payout.select_type,
                    ),
                ],
                PayoutStates.ENTER_AMOUNT: [
                    MessageHandler(
                        filters.TEXT & (~filters.COMMAND),
                        payout.enter_amount,
                    ),
                ],
                PayoutStates.SELECT_METHOD: [
                    MessageHandler(
                        filters.TEXT & (~filters.COMMAND),
                        payout.select_method,
                    ),
                ],
                PayoutStates.CONFIRM_CARD: [
                    CallbackQueryHandler(payout.confirm_card),
                ],
            },
            fallbacks=[],
            allow_reentry=True,
        )
    )


__all__ = [name for name in globals() if not name.startswith("_")]
