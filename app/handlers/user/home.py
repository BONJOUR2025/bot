from telegram import ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes, ConversationHandler
from ...utils.logger import log
from ...services.users import load_users_map
from ...keyboards.reply_user import get_main_menu


# Незнакомцу (бот запущен, но к карточке сотрудника не привязан) меню не
# показываем вовсе: кнопки всё равно ничего не умеют без профиля и только
# вводят в заблуждение. Клавиатуру убираем — она могла остаться от прошлого.
WAITING_LINK_TEXT = (
    "⏳ Ожидайте привязку.\n\n"
    "Администратор привяжет бота к вашему профилю сотрудника — после этого здесь появится меню."
)


async def reply_waiting_link(update: Update) -> None:
    if update.message:
        await update.message.reply_text(WAITING_LINK_TEXT, reply_markup=ReplyKeyboardRemove())


async def get_user_info_user(update: Update,
                             context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выводит главное меню сотрудника."""
    user_id = str(update.effective_user.id)
    users = load_users_map()
    user = users.get(user_id)
    if not user:
        await reply_waiting_link(update)
        return
    name = user.get("name", "Пользователь")
    greeting_text = f"Приветствую тебя, {name}!\n\nВыберите действие:"
    if update.message:
        await update.message.reply_text(greeting_text, reply_markup=get_main_menu(user_id))


async def home_handler_user(update: Update,
                            context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    state = context.application.chat_data.get(chat_id, {}).get("conversation")
    log(f"[FSM] state before entry: {state}")
    log(
        f"DEBUG [home_handler] Получено сообщение: '{update.message.text if update.message else ''}'"
    )
    context.user_data.clear()
    if str(update.effective_user.id) not in load_users_map():
        await reply_waiting_link(update)
        return ConversationHandler.END
    if update.message:
        await update.message.reply_text(
            "🏠 Вы вернулись в главное меню.",
            reply_markup=get_main_menu(str(update.effective_user.id)),
        )
    return ConversationHandler.END
