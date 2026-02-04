from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from ..config import ADMIN_ID
from ..keyboards.reply_admin import get_admin_menu
from ..keyboards.reply_user import get_main_menu
from ..utils.logger import log

RESET_TEXTS = {"🏠 Домой", "🔙 Назад", "❌ Отмена", "Назад", "Отмена"}


async def global_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Clear all conversation data and return to the main menu."""
    state_data = dict(context.user_data)
    cleared_states = {}

    # Clean active conversations for this user/chat
    app = context.application
    for handler, conversations in app._conversation_handler_conversations.items():
        key = handler._get_key(update)
        if key in conversations:
            cleared_states[handler.name or handler.__class__.__name__] = conversations.pop(key)

    log(
        f"🔄 [global_reset] state_data before reset: {state_data}, "
        f"cleared_states: {cleared_states}"
    )
    context.user_data.clear()

    user_id = str(update.effective_user.id) if update.effective_user else None
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(
            "🏠 Главное меню", reply_markup=get_admin_menu()
        )
    else:
        await update.message.reply_text(
            "🏠 Вы вернулись в главное меню.", reply_markup=get_main_menu(user_id)
        )
    return ConversationHandler.END
