"""Standalone quick-task creation via free-text input."""
import json
import logging
import re
from datetime import date as date_cls, time as time_cls, datetime as dt_cls

from telegram.ext import ConversationHandler, MessageHandler, CommandHandler, filters

log = logging.getLogger(__name__)

QUICK_TASK_TEXT = 77  # ConversationHandler state


async def quick_task_entry(update, context):
    await update.message.reply_text(
        "📝 <b>Создание задачи</b>\n\n"
        "Напишите задачу в свободной форме, например:\n"
        "• «напомни завтра в 13:00 связаться с Арменом и обсудить детали сделки»\n"
        "• «позвонить в банк в пятницу в 10:00»\n"
        "• «встреча с партнёрами 5 июня в 15:30»\n\n"
        "/cancel — отменить",
        parse_mode="HTML",
    )
    return QUICK_TASK_TEXT


async def quick_task_handle_text(update, context):
    text = update.message.text.strip()
    await update.message.reply_text("⏳ Обрабатываю...")

    from app.services.config_service import ConfigService
    from app.services.task_service import get_task_service
    from app.schemas.task import TaskCreate

    cfg = ConfigService().load()
    from app.services.llm_client import chat, get_client
    if not get_client(cfg):
        await update.message.reply_text("❌ API key не настроен в настройках.")
        return ConversationHandler.END

    today_str = date_cls.today().isoformat()
    prompt = (
        f"Сегодня {today_str}.\n"
        "Извлеки из текста поля задачи и верни ТОЛЬКО JSON (без markdown):\n"
        '{"title": "краткое название задачи", '
        '"description": "описание или null", '
        '"due_date": "YYYY-MM-DD или null", '
        '"due_time": "HH:MM или null"}\n\n'
        "Правила:\n"
        "— Преобразуй относительные даты (завтра, в пятницу, 5 июня) в абсолютные\n"
        "— Если время не указано — null\n"
        "— title должен быть коротким (до 60 символов)\n\n"
        f"Текст: «{text}»"
    )

    try:
        raw = chat(cfg, [{"role": "user", "content": prompt}], max_tokens=200)
        if not raw:
            raise ValueError("empty response")
    except Exception as e:
        log.warning("quick_task: LLM failed: %s", e)
        await update.message.reply_text("❌ Ошибка при обращении к AI. Попробуйте позже.")
        return ConversationHandler.END

    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        await update.message.reply_text("❌ Не удалось разобрать ответ. Попробуйте переформулировать.")
        return ConversationHandler.END

    try:
        data = json.loads(m.group())
    except json.JSONDecodeError:
        await update.message.reply_text("❌ Ошибка при разборе JSON. Попробуйте переформулировать.")
        return ConversationHandler.END

    due_date = None
    due_time_val = None
    if data.get("due_date"):
        try:
            due_date = date_cls.fromisoformat(data["due_date"])
        except Exception:
            pass
    if data.get("due_time"):
        try:
            h, mn = data["due_time"].split(":")
            due_time_val = time_cls(int(h), int(mn))
        except Exception:
            pass

    title = (data.get("title") or text[:60]).strip()
    description = (data.get("description") or "").strip() or None

    try:
        await get_task_service().create_task(TaskCreate(
            title=title,
            description=description,
            due_date=due_date,
            due_time=due_time_val,
            priority="medium",
            category="Общее",
        ), created_by="admin")
    except Exception as e:
        log.warning("quick_task: create_task failed: %s", e)
        await update.message.reply_text(f"❌ Не удалось создать задачу: {e}")
        return ConversationHandler.END

    parts = [f"✅ <b>Задача создана:</b> {title}"]
    if due_date:
        date_str = due_date.strftime("%d.%m.%Y")
        time_str = f" в {due_time_val.strftime('%H:%M')}" if due_time_val else ""
        parts.append(f"📅 {date_str}{time_str}")
    if description:
        parts.append(f"📋 {description}")

    await update.message.reply_text("\n".join(parts), parse_mode="HTML")
    return ConversationHandler.END


async def quick_task_cancel(update, context):
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END


def build_quick_task_handler(admin_id: int):
    admin_filter = filters.User(admin_id)
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^📝 Задача$") & admin_filter, quick_task_entry)
        ],
        states={
            QUICK_TASK_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, quick_task_handle_text)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", quick_task_cancel),
            MessageHandler(filters.Regex(r"^🏠 Домой$"), quick_task_cancel),
        ],
        per_chat=True,
        allow_reentry=True,
    )
