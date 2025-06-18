from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from ...utils.logger import log
from ...services.users import load_users
from ...keyboards.reply_user import get_main_menu


async def get_user_info_user(update: Update,
                             context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выводит главное меню сотрудника."""
    user_id = str(update.effective_user.id)
    users = load_users()
    user = users.get(user_id)
    if not user:
        if update.message:
            await update.message.reply_text(
                "Информация о пользователе не найдена. Обратитесь к администратору.",
                reply_markup=get_main_menu(),
            )
        return
    name = user.get("name", "Пользователь")
    greeting_text = f"Приветствую тебя, {name}!\n\nВыберите действие:"
    if update.message:
        await update.message.reply_text(greeting_text, reply_markup=get_main_menu())


async def home_handler_user(update: Update,
                            context: ContextTypes.DEFAULT_TYPE) -> int:
    log(
        f"DEBUG [home_handler] Получено сообщение: '{
            update.message.text if update.message else ''}'")
    context.user_data.clear()
    if update.message:
        await update.message.reply_text(
            "🏠 Вы вернулись в главное меню.",
            reply_markup=get_main_menu(),
        )
    return ConversationHandler.END
