from telegram import Update
from telegram.ext import ContextTypes
from ...utils.logger import log, log_connection
from ...config import ADMIN_ID
from ...data.bot_user_repository import get_bot_user_repository
from .home import get_user_info_user
from ...services.users import load_users_map
from ..admin import admin


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /start"""
    user_id = update.effective_user.id if update.effective_user else None
    if update.effective_user:
        user = update.effective_user
        username = f"@{user.username}" if user.username else user.full_name
        payload = (context.args or [""])[0] if getattr(context, "args", None) else ""
        requested = payload[4:] if payload.startswith("emp_") else None
        get_bot_user_repository().touch(
            user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            requested_employee_id=requested,
        )
        if requested and str(user.id) not in load_users_map():
            log_connection(f"Bot: /start from {user.id} ({username}) по ссылке из кабинета, сотрудник {requested}")
            if update.message:
                await update.message.reply_text(
                    "✅ Бот запущен. Администратор привяжет его к вашему профилю — "
                    "после этого сюда будут приходить уведомления о заказах и работе."
                )
            return
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
