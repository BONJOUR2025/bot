from telegram import Update
from telegram.ext import ContextTypes
from ...utils.logger import log
from ...config import ADMIN_ID
from ...data.bot_user_repository import get_bot_user_repository
from .home import get_user_info_user
from ..admin import admin


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /start"""
    user_id = update.effective_user.id if update.effective_user else None
    if update.effective_user:
        get_bot_user_repository().touch(
            update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
        )
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
