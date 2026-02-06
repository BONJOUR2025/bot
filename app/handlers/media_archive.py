"""
Обработчик для сохранения медиафайлов, отправленных пользователями.
Фото, видео, документы, голосовые и видеосообщения сохраняются
в папку media_archive без уведомления пользователя.
"""

import os
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from ..utils.logger import log

# Папка для сохранения медиа
MEDIA_DIR = Path(__file__).parent.parent.parent / "media_archive"


def _ensure_dir():
    """Создаёт папку media_archive если её нет."""
    MEDIA_DIR.mkdir(exist_ok=True)


def _generate_filename(user_id: int, username: str | None, ext: str) -> str:
    """Генерирует имя файла: timestamp_userid_username.ext"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    uname = username or "unknown"
    return f"{ts}_{user_id}_{uname}.{ext}"


async def archive_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Сохраняет медиафайл в папку media_archive.
    Работает тихо — пользователь не получает никакого ответа.
    """
    message = update.message
    if not message:
        return

    user = message.from_user
    user_id = user.id if user else 0
    username = user.username if user else None

    _ensure_dir()

    file_obj = None
    ext = "bin"

    # Определяем тип медиа и расширение
    if message.photo:
        # Берём фото максимального размера
        file_obj = message.photo[-1]
        ext = "jpg"
    elif message.video:
        file_obj = message.video
        ext = "mp4"
    elif message.video_note:
        file_obj = message.video_note
        ext = "mp4"
    elif message.voice:
        file_obj = message.voice
        ext = "ogg"
    elif message.audio:
        file_obj = message.audio
        ext = message.audio.file_name.split(".")[-1] if message.audio.file_name else "mp3"
    elif message.document:
        file_obj = message.document
        if message.document.file_name:
            ext = message.document.file_name.split(".")[-1]
        else:
            ext = "bin"
    elif message.sticker:
        file_obj = message.sticker
        ext = "webp"
    elif message.animation:
        file_obj = message.animation
        ext = "mp4"

    if not file_obj:
        return

    try:
        tg_file = await file_obj.get_file()
        filename = _generate_filename(user_id, username, ext)
        filepath = MEDIA_DIR / filename
        await tg_file.download_to_drive(filepath)
        log(f"📁 [media_archive] Сохранён файл: {filename} от {user_id} (@{username})")
    except Exception as e:
        log(f"⚠️ [media_archive] Ошибка сохранения: {e}")
