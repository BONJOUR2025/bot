"""Employee knowledge base Q&A via Telegram bot."""
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

log = logging.getLogger(__name__)

KB_CHAT = 1
_EXIT_PHRASES = {"🏠 домой", "🏠 домой", "/start", "/cancel"}

KB_KEYBOARD = ReplyKeyboardMarkup(
    [["🏠 Домой"]],
    resize_keyboard=True,
    one_time_keyboard=False,
)


async def handle_kb_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User pressed '📚 База знаний' — enter Q&A mode."""
    await update.message.reply_text(
        "📚 Режим базы знаний\n\n"
        "Задайте ваш вопрос — я отвечу на основе регламентов и инструкций компании.\n"
        "Нажмите 🏠 Домой чтобы выйти.",
        reply_markup=KB_KEYBOARD,
    )
    return KB_CHAT


async def handle_kb_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Answer employee question using the knowledge base."""
    text = (update.message.text or "").strip()

    if text.lower() in _EXIT_PHRASES or text == "🏠 Домой":
        from app.config import ADMIN_ID
        user_id = str(update.effective_user.id)
        if str(update.effective_user.id) == str(ADMIN_ID):
            from app.keyboards.reply_admin import get_admin_menu
            await update.message.reply_text("🏠 Главное меню", reply_markup=get_admin_menu())
        else:
            from app.keyboards.reply_user import get_main_menu
            await update.message.reply_text("🏠 Вы вернулись в главное меню.", reply_markup=get_main_menu(user_id))
        return ConversationHandler.END

    await update.message.chat.send_action("typing")

    try:
        kb_text, cfg = _load_kb_and_cfg()
    except Exception as e:
        await update.message.reply_text(f"⚠️ {e}", reply_markup=KB_KEYBOARD)
        return KB_CHAT

    system = f"""Ты корпоративный AI-ассистент. Отвечай на вопросы сотрудников строго на основе базы знаний ниже.

База знаний компании:
{kb_text}

Правила:
1. Отвечай только на основе базы знаний. Не придумывай.
2. Если ответа в базе нет — скажи: «Эта информация не найдена в базе знаний. Обратитесь к руководителю.»
3. Пиши кратко и по делу. Без форматирования (никаких **, *, #).
4. Пиши на русском, обращайся на «вы»."""

    try:
        from app.services.llm_client import chat
        reply = chat(cfg, [{"role": "user", "content": text}], system=system, max_tokens=600) or ""
        reply = reply.replace("**", "").replace("__", "").strip()
    except Exception as e:
        log.warning("KB AI error: %s", e)
        await update.message.reply_text(
            "⚠️ Ошибка AI. Попробуйте позже или обратитесь к руководителю.",
            reply_markup=KB_KEYBOARD,
        )
        return KB_CHAT

    await update.message.reply_text(reply, reply_markup=KB_KEYBOARD)
    return KB_CHAT


def _load_kb_and_cfg():
    from app.db.session import SessionLocal
    from app.models.knowledge import KnowledgeDocument
    from app.services.config_service import ConfigService
    from app.services.llm_client import get_client

    cfg = ConfigService().load()
    if not get_client(cfg):
        raise ValueError("API Key не настроен. Обратитесь к администратору.")

    db = SessionLocal()
    try:
        docs = db.query(KnowledgeDocument).order_by(
            KnowledgeDocument.order_idx, KnowledgeDocument.id
        ).all()
        parts = []
        for d in docs:
            if d.content and d.content.strip():
                parts.append(f"=== {d.title} ({d.category}) ===\n{d.content.strip()}")
        kb_text = "\n\n".join(parts)
    finally:
        db.close()

    if not kb_text:
        raise ValueError("База знаний пуста. Обратитесь к администратору.")

    return kb_text, cfg
