from telegram import Update
from telegram.ext import ContextTypes

from ..utils.logger import log, log_user_action


def _user_label(user) -> str:
    return f"@{user.username}" if user.username else user.full_name


async def log_button_press(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log all callback button presses."""
    query = update.callback_query
    if not query:
        return
    user = query.from_user
    username = _user_label(user)
    log(f"[button] {user.id} ({username}) pressed: {query.data}")
    log_user_action(user.id, username, "нажал кнопку", data=query.data)


def _describe_message(message) -> str:
    if message.text:
        text = message.text.replace("\n", " ")
        if len(text) > 300:
            text = text[:300] + "…"
        return f'отправил сообщение: "{text}"'
    if message.photo:
        return "отправил фото"
    if message.video:
        return "отправил видео"
    if message.voice:
        return "отправил голосовое сообщение"
    if message.document:
        return f"отправил документ: {message.document.file_name}"
    if message.location:
        return "отправил геолокацию"
    if message.sticker:
        return "отправил стикер"
    return f"отправил сообщение ({message.effective_attachment.__class__.__name__})"


async def log_user_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log every incoming message from a user to their personal log file."""
    message = update.effective_message
    user = update.effective_user
    if not user or not message:
        return
    log_user_action(user.id, _user_label(user), _describe_message(message))
