from telegram import Update
from telegram.ext import ContextTypes
from ...utils.logger import log
from ...services.telegram_service import TelegramService
from ...services.message_service import MessageService


async def handle_acknowledgment(update: Update,
                                context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer("✅ Отмечено как прочитано", show_alert=True)
    try:
        text = query.message.text or query.message.caption or ""
        if "✅ Принято" not in text:
            text = text + "\n\n✅ Принято"
        if query.message.photo:
            await query.edit_message_caption(
                text, parse_mode="HTML", reply_markup=None
            )
        else:
            await query.edit_message_text(
                text, parse_mode="HTML", reply_markup=None
            )
    except Exception as exc:
        log(f"Ack edit failed: {exc}")
    TelegramService.update_sent_message_status(
        query.from_user.id, query.message.message_id, "принято"
    )
    MessageService.accept_by_details(
        query.from_user.id, query.message.message_id)
