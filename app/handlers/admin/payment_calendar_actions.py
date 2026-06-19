from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from app.data.payment_calendar_repository import PaymentCalendarRepository
from app.services.payment_calendar_text import build_invoice_text


async def handle_payment_calendar_paid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cashier presses '✅ Оплачено' on a payment-calendar invoice message."""
    query = update.callback_query
    record_id = query.data[len("paycal_paid_"):]
    record = PaymentCalendarRepository().update_record(
        int(record_id), {"status": "paid", "paid_at": datetime.utcnow()}
    )
    if record is None:
        await query.answer("Запись не найдена", show_alert=True)
        return

    await query.answer("✅ Отмечено как оплачено")
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    # Rebuild the original markdown from the schedule data instead of reusing
    # query.message.text/caption — Telegram returns those with markdown syntax
    # already stripped (entities, not literal "*"/"```"), so re-parsing them
    # with parse_mode would lose the original formatting.
    text = build_invoice_text(record["schedule"]) + f"\n\n✅ *Оплачено* {now}"
    try:
        if query.message.caption is not None:
            await query.edit_message_caption(caption=text, parse_mode="Markdown")
        else:
            await query.edit_message_text(text=text, parse_mode="Markdown")
    except Exception:
        pass
