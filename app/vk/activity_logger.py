"""Per-user activity logging for the VK bot — mirrors
app/handlers/callback_logger.py's log_user_activity for Telegram, so VK
activity shows up the same way in logs/users/<id>...log and the general
log, instead of being invisible next to the Telegram side."""

from __future__ import annotations

from vkbottle.bot import Message

from ..utils.logger import log, log_user_action

ATTACHMENT_LABELS = {
    "photo": "отправил фото",
    "video": "отправил видео",
    "audio": "отправил аудио",
    "audio_message": "отправил голосовое сообщение",
    "doc": "отправил документ",
    "sticker": "отправил стикер",
    "wall": "переслал запись со стены",
    "link": "отправил ссылку",
    "market": "отправил товар",
    "gift": "отправил подарок",
    "graffiti": "отправил граффити",
    "poll": "отправил опрос",
}


def describe_message(message: Message) -> str:
    if message.geo:
        return "отправил геолокацию"
    if message.text:
        text = message.text.replace("\n", " ")
        if len(text) > 300:
            text = text[:300] + "…"
        return f'отправил сообщение: "{text}"'
    for attachment in message.attachments or []:
        label = ATTACHMENT_LABELS.get(attachment.type)
        if label:
            return label
    return "отправил сообщение (вложение)"


def log_activity(message: Message, employee_id: str | None, employee_name: str | None) -> None:
    """user_id for the per-user log is the employee id when the VK contact
    is already linked (so their VK and Telegram activity share one log
    file), or a "vk_<id>"-prefixed pseudo-id otherwise — VK ids are plain
    numbers, same shape as Telegram ids, so leaving it unprefixed risks two
    different people from different platforms colliding on one log file."""
    key = employee_id or f"vk_{message.from_id}"
    label = employee_name or f"VK id {message.from_id}"
    description = describe_message(message)
    log(f"[vk] {key} ({label}) {description}")
    log_user_action(key, label, description)
