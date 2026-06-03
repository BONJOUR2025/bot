"""Admin conversation: fill in vacancy knowledge base gaps via Telegram."""
import logging
import re
from datetime import datetime

from telegram.ext import ConversationHandler, CallbackQueryHandler, MessageHandler, CommandHandler, filters

log = logging.getLogger(__name__)

SETUP_ANSWER = 91


async def handle_setup_callback(update, context):
    query = update.callback_query
    await query.answer()
    vacancy_id = int(query.data.split("_")[-1])
    context.user_data["setup_vacancy_id"] = vacancy_id

    from app.db.session import SessionLocal
    from app.models.recruitment import Vacancy
    from app.services.config_service import ConfigService
    from app.services.vacancy_readiness import get_missing_questions

    db = SessionLocal()
    try:
        v = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
        title = v.title if v else f"#{vacancy_id}"
    finally:
        db.close()

    cfg = ConfigService().load()
    questions = await get_missing_questions(v, cfg) if v else []
    context.user_data["setup_questions"] = questions

    q_text = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions)) if questions else "(все данные уже есть)"

    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(
        f"✏️ <b>Вакансия «{title}»</b>\n\n"
        f"Ответьте на вопросы в одном сообщении в свободной форме:\n\n"
        f"{q_text}\n\n"
        f"Пример: «Deal-breakers: офис обязателен, только РФ. Зарплата: 120–180к. "
        f"Первые 3 месяца: онбординг, правка багов, первый модуль самостоятельно.»\n\n"
        f"/cancel — отмена",
        parse_mode="HTML",
    )
    return SETUP_ANSWER


async def handle_setup_answer(update, context):
    vacancy_id = context.user_data.pop("setup_vacancy_id", None)
    questions = context.user_data.pop("setup_questions", [])
    if not vacancy_id:
        return ConversationHandler.END

    answer = update.message.text.strip()
    await update.message.reply_text("⏳ Обновляю базу знаний...")

    from app.db.session import SessionLocal
    from app.models.recruitment import Vacancy
    from app.services.config_service import ConfigService
    from app.services.llm_client import chat

    db = SessionLocal()
    try:
        v = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
        if not v:
            await update.message.reply_text("❌ Вакансия не найдена.")
            return ConversationHandler.END

        cfg = ConfigService().load()
        current_kb = (v.knowledge_base or "").strip()
        q_context = "\n".join(f"- {q}" for q in questions)

        prompt = (
            f"Вакансия: {v.title}\n"
            f"Текущая база знаний:\n{current_kb or '(пусто)'}\n\n"
            f"Рекрутер ответил на вопросы:\n{q_context}\n\n"
            f"Ответ рекрутера: {answer}\n\n"
            "Обнови базу знаний: сохрани всё что уже было, добавь новое. "
            "Структурируй по разделам: Deal-breakers | Зарплата | Задачи первых 3 месяцев | "
            "Этапы найма | Остальное.\n"
            "Верни ТОЛЬКО обновлённый текст базы знаний — без пояснений."
        )

        updated_kb = chat(cfg, [{"role": "user", "content": prompt}], max_tokens=1000)
        if not updated_kb:
            await update.message.reply_text("❌ Ошибка AI. Попробуйте позже.")
            return ConversationHandler.END

        v.knowledge_base = updated_kb
        v.updated_at = datetime.utcnow()
        db.commit()

        preview = updated_kb[:600] + ("..." if len(updated_kb) > 600 else "")
        await update.message.reply_text(
            f"✅ <b>База знаний вакансии «{v.title}» обновлена.</b>\n\n"
            f"<code>{preview}</code>",
            parse_mode="HTML",
        )
    finally:
        db.close()

    return ConversationHandler.END


async def cancel_setup(update, context):
    context.user_data.pop("setup_vacancy_id", None)
    context.user_data.pop("setup_questions", None)
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END


def build_vacancy_setup_handler():
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_setup_callback, pattern=r"^vsetup_\d+$")],
        states={
            SETUP_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_setup_answer)],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, cancel_setup)],
        },
        fallbacks=[CommandHandler("cancel", cancel_setup)],
        per_chat=True,
        allow_reentry=True,
        conversation_timeout=300,
    )
    return conv
