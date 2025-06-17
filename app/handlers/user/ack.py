from telegram import Update
from telegram.ext import ContextTypes
from ...utils.logger import log

async def handle_acknowledgment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer("Отмечено как прочитано ✅", show_alert=True)
    try:
        await query.edit_message_reply_markup(None)
    except Exception as exc:
        log(f"Ack edit failed: {exc}")
