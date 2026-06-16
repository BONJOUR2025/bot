from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from app.data.asset_repository import AssetRepository


async def handle_asset_ack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Employee presses '✅ Подтвердить получение' on an asset notification."""
    query = update.callback_query
    await query.answer("✅ Получение подтверждено")
    item_id = query.data[len("asset_ack_"):]
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    AssetRepository().update(item_id, {"acked_at": now})
    original = (query.message.text or "").rstrip()
    new_text = original + f"\n\n✅ Получение подтверждено {now}"
    try:
        await query.edit_message_text(new_text, parse_mode="HTML", reply_markup=None)
    except Exception:
        pass
