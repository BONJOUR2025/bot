from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from app.data.payment_calendar_repository import PaymentCalendarRepository


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
    mark = f"\n\n✅ *Оплачено* {now}"
    try:
        if query.message.caption is not None:
            await query.edit_message_caption(
                caption=(query.message.caption or "") + mark, parse_mode="Markdown", reply_markup=None
            )
        else:
            await query.edit_message_text(
                text=(query.message.text or "") + mark, parse_mode="Markdown", reply_markup=None
            )
    except Exception:
        pass
