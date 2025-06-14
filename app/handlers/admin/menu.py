import datetime
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from ...constants import UserStates
from ...config import ADMIN_ID
from ...keyboards.reply_admin import get_admin_menu
from ...utils.logger import log

# Глобальная переменная для режима администратора
admin_mode = {}


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вход в режим администратора."""
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        log(f"🛂 [admin] Вход в функцию, user_id: {user_id}")
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return ConversationHandler.END
    admin_mode[user_id] = True
    await update.message.reply_text(
        "✅ Добро пожаловать, администратор!", reply_markup=get_admin_menu()
    )
    return UserStates.SELECT_DATA_TYPE


async def home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню администратора."""
    context.user_data.clear()
    log(
        f"DEBUG [home_callback] Сброс состояний для user_id: {update.effective_user.id}"
    )
    await update.message.reply_text(
        "🏠 Главное меню", reply_markup=get_admin_menu()
    )
    return ConversationHandler.END


async def exit_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершает режим администратора."""
    user_id = str(update.effective_user.id)
    if admin_mode.get(user_id):
        admin_mode.pop(user_id)
        await update.message.reply_text(
            "🚪 Вы вышли из режима администратора.", reply_markup=None
        )
        log(f"Пользователь {user_id} вышел из режима АДМИН.")
    else:
        await update.message.reply_text("❌ Вы не в режиме администратора.")

