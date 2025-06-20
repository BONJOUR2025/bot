from ...keyboards.reply_admin import get_admin_menu
from ...constants import UserStates
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update
from telegram.error import BadRequest
from ...utils.logger import log
import datetime
from ...config import ADMIN_CHAT_ID
from ...services.users import load_users
from telegram.ext import Application


async def check_birthdays(app: Application):
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)

    users = load_users()

    for uid, user in users.items():
        bdate_str = user.get("birthdate")
        if not bdate_str:
            continue
        try:
            bdate = datetime.datetime.strptime(bdate_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        name = user.get("name", "Без имени")
        if (bdate.day, bdate.month) == (today.day, today.month):
            log(
                f"[Telegram] birthday notification for today to {ADMIN_CHAT_ID} — {name}"
            )
            try:
                await app.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"🎉 Сегодня день рождения у {name}!",
                )
            except BadRequest as e:
                log(f"❌ Failed to send message to chat {ADMIN_CHAT_ID} — {e}")
                raise
        elif (bdate.day, bdate.month) == (tomorrow.day, tomorrow.month):
            log(
                f"[Telegram] birthday notification for tomorrow to {ADMIN_CHAT_ID} — {name}"
            )
            try:
                await app.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"📅 Завтра день рождения у {name}",
                )
            except BadRequest as e:
                log(f"❌ Failed to send message to chat {ADMIN_CHAT_ID} — {e}")
                raise


async def show_birthdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображает список ближайших дней рождений сотрудников."""
    users = load_users()
    today = datetime.date.today()
    upcoming = []
    for user in users.values():
        bdate_str = user.get("birthdate")
        if not bdate_str:
            continue
        try:
            bdate = datetime.datetime.strptime(bdate_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        next_bday = bdate.replace(year=today.year)
        if next_bday < today:
            next_bday = next_bday.replace(year=today.year + 1)
        diff = (next_bday - today).days
        upcoming.append((diff, next_bday, user.get("name", "Без имени")))
    upcoming.sort(key=lambda x: x[0])
    lines = [
        f"{date.strftime('%d.%m')} - {name}" for _, date, name in upcoming
    ]
    text = "🎂 Ближайшие дни рождения:\n" + (
        "\n".join(lines) if lines else "Нет данных"
    )
    await update.message.reply_text(text, reply_markup=get_admin_menu())
    return UserStates.SELECT_DATA_TYPE
