from telegram.ext import ConversationHandler, MessageHandler, filters

from app.constants import PAYMENT_REQUEST_PATTERN

from .start import get_user_info_user, start
from .home import home_handler_user
from .menu import (
    view_salary_user,
    view_schedule_user,
    handle_selected_month_user,
    handle_schedule_request,
)
from .payout import (
    request_payout_user,
    request_payout_start,
    handle_payout_type_user,
    handle_payout_amount_user,
    payout_method_user,
    confirm_payout_user,
    handle_card_confirmation,
    change_payout_amount,
    change_payout_type,
    change_payout_method,
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
from app.core.types import PayoutStates


def register_user_handlers(application):
    """Register conversation handlers for regular users."""
    application.add_handler(
        ConversationHandler(
            entry_points=[
                MessageHandler(
                    filters.TEXT
                    & filters.Regex(PAYMENT_REQUEST_PATTERN),
                    request_payout_user,
                )
            ],
            states={
                PayoutStates.SELECT_TYPE: [
                    MessageHandler(filters.TEXT, handle_payout_type_user)
                ],
                PayoutStates.ENTER_AMOUNT: [
                    MessageHandler(filters.TEXT, handle_payout_amount_user)
                ],
                PayoutStates.SELECT_METHOD: [
                    MessageHandler(filters.TEXT, payout_method_user)
                ],
            },
            fallbacks=[],
        )
    )


__all__ = [name for name in globals() if not name.startswith("_")]
