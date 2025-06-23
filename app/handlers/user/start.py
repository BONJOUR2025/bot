from telegram import Update
from telegram.ext import ContextTypes
from ...utils.logger import log
from ...config import ADMIN_ID
from .home import get_user_info_user
from ..admin import admin


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /start"""
    user_id = update.effective_user.id if update.effective_user else None
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
