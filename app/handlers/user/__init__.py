

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


def register_user_handlers(application):
    """Register conversation handlers for regular users."""
    # Payout requests for regular users have been removed.
    pass


__all__ = [name for name in globals() if not name.startswith("_")]
