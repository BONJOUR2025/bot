from telegram import Update
from telegram.ext import ContextTypes

from ..utils.logger import log


async def log_button_press(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log all callback button presses."""
    query = update.callback_query
    if not query:
        return
    user = query.from_user
    username = f"@{user.username}" if user.username else user.full_name
    log(f"[button] {user.id} ({username}) pressed: {query.data}")
