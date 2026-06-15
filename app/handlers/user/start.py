from telegram import Update
from telegram.ext import ContextTypes
from ...utils.logger import log, log_connection
from ...config import ADMIN_ID
from ...data.bot_user_repository import get_bot_user_repository
from .home import get_user_info_user
from ..admin import admin


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /start"""
    user_id = update.effective_user.id if update.effective_user else None
    if update.effective_user:
        user = update.effective_user
        username = f"@{user.username}" if user.username else user.full_name
        get_bot_user_repository().touch(
            user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        log_connection(f"Bot: /start from {user.id} ({username})")
    try:
        if user_id == ADMIN_ID:
            await admin(update, context)
        else:
            await get_user_info_user(update, context)
    except Exception as e:
        log(f"❌ Ошибка в /start для user_id {user_id}: {e}")
        if update.message:
            await update.message.reply_text(
                "❌ Произошла ошибка. Попробуйте позже."
            )
