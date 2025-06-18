from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ...config import ADMIN_ID, CARD_DISPATCH_CHAT_ID
from ...keyboards.reply_admin import get_admin_menu
from ...services.advance_requests import load_advance_requests, save_advance_requests
from ...services.users import load_users
from ...utils.logger import log


async def allow_payout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.data.split("_")[-1]
    log(f"✅ [allow_payout] Одобрение выплаты для user_id: {user_id}")

    requests = load_advance_requests()
    req = next((r for r in requests if r["user_id"] == user_id and r["status"] == "Ожидает"), None)
    if not req:
        await query.edit_message_text("❌ Нет активного запроса для одобрения.")
        return

    req["status"] = "Разрешено"
    save_advance_requests(requests)
    updated_text = f"{query.message.text}\n\n✅ Разрешено"
    await query.edit_message_text(updated_text)
    if req["method"] == "💳 На карту":
        payout_type = req.get("payout_type", "Не указано")
            f"👤 {req['name']}\n"
            f"📱 {req['phone']}\n"
            f"🏦 {req['bank']}\n"
            f"💰 {req['amount']} ₽\n"
        buttons = InlineKeyboardMarkup(
            await context.bot.send_message(
                chat_id=CARD_DISPATCH_CHAT_ID,
                text=cashier_text,
                reply_markup=buttons,
            )
        except Exception as e:
            log(f"❌ [allow_payout] Ошибка отправки кассиру: {e}")


async def deny_payout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.data.split("_")[-1]
    log(f"❌ [deny_payout] Отклонение выплаты для user_id: {user_id}")

    requests = load_advance_requests()
    req = next((r for r in requests if r["user_id"] == user_id and r["status"] == "Ожидает"), None)
    if not req:
        await query.edit_message_text("❌ Нет активного запроса для отклонения.")
        return

    req["status"] = "Отказано"
    save_advance_requests(requests)
    updated_text = f"{query.message.text}\n\n❌ Отказано"
    await query.edit_message_text(updated_text)
    requests = load_advance_requests()
    pending_requests = [r for r in requests if r.get("status") == "Ожидает"]
    for r in pending_requests:
        r["status"] = "Отменено"
    if pending_requests:
        save_advance_requests(requests)

    await update.message.reply_text("✅ Сброс выполнен", reply_markup=get_admin_menu())


async def mark_sent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.data.split("_")[-1]
    updated_text = f"{query.message.text}\n\n📤 Отправлено"
    await query.edit_message_text(updated_text)
    message_lines = []
    if pending_requests:
        message_lines.append(f"✅ Сброшено {len(pending_requests)} запросов из файла:")
        message_lines.extend([f"Запрос #{i+1}:\n{detail}" for i, detail in enumerate(reset_details)])
    else:
        message_lines.append("📭 Нет активных запросов в файле.")

    if reset_users:
        message_lines.append(f"\n✅ Очищено {len(reset_users)} зависших состояний:")
        message_lines.extend([f"Пользователь #{i+1}: {user}" for i, user in enumerate(reset_users)])
    else:
        message_lines.append("\n📭 Нет зависших состояний у пользователей.")

    reset_message = "\n\n".join(message_lines)
    await update.message.reply_text(reset_message, reply_markup=get_admin_menu())
    log(f"✅ [reset_payout_request] Завершён сброс: {reset_message}")


async def mark_sent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.data.split("_")[-1]
    current_text = query.message.text
    updated_text = f"{current_text}\n\n📤 Отправлено"

    await query.edit_message_text(updated_text)
