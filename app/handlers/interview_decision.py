"""Handles inline-button decisions and free-text instructions for interview scheduling."""
import json
import logging
import re
from datetime import datetime, date as date_cls, time as time_cls

from telegram.ext import ConversationHandler, CallbackQueryHandler, MessageHandler, CommandHandler, filters

log = logging.getLogger(__name__)

INSTRUCTION_WAITING = 42  # ConversationHandler state

_MONTHS_RU = ["января","февраля","марта","апреля","мая","июня",
               "июля","августа","сентября","октября","ноября","декабря"]

DEFAULT_INTERVIEW_TPL = (
    "Здравствуйте, #name!\n"
    "Приглашаем вас на собеседование.\n"
    "📅 Дата: #date\n🕐 Время: #time\n📍 Место: #place\n\n"
    "Если возникнут вопросы — напишите в этот чат."
)


def _fmt_date(iso: str) -> str:
    d = date_cls.fromisoformat(iso)
    return f"{d.day} {_MONTHS_RU[d.month - 1]} {d.year} г."


def _apply_tpl(tpl: str, name: str, date: str, time: str, place: str) -> str:
    return (
        tpl
        .replace("#name", name.split()[0] if name else "Здравствуйте")
        .replace("#date", _fmt_date(date) if date else "#date")
        .replace("#time", time or "#time")
        .replace("#place", place or "#place")
    )



async def _finalize_interview(candidate_id: int):
    """Move candidate to 'собеседование', send template, create task. Used by both confirm and instruction flow."""
    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate, TelegramMessage
    from app.services.config_service import ConfigService
    from app.services.notify import send_secretary_message
    from app.services.task_service import get_task_service
    from app.schemas.task import TaskCreate

    db = SessionLocal()
    try:
        c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not c:
            return "Кандидат не найден."

        interview_date = c.pending_interview_date or ""
        interview_time = c.pending_interview_time or ""
        place = c.pending_interview_place or ""

        cfg = ConfigService().load()
        saved_tpls = cfg.get("message_templates") or []
        tpl = next((t.get("text", "") for t in saved_tpls if t.get("type") == "interview"), "")
        tpl = tpl.strip() or DEFAULT_INTERVIEW_TPL

        msg_text = _apply_tpl(tpl, c.name or "", interview_date, interview_time, place)

        err = await send_secretary_message(c.telegram_chat_id, msg_text)
        if not err:
            out = TelegramMessage(candidate_id=candidate_id, direction="out", text=msg_text, sent_by_ai=1)
            db.add(out)

        c.stage = "собеседование"
        c.pending_interview_date = None
        c.pending_interview_time = None
        c.pending_interview_place = None
        c.updated_at = datetime.utcnow()
        db.commit()

        # Create task
        due_date = None
        due_time_val = None
        if interview_date:
            try: due_date = date_cls.fromisoformat(interview_date)
            except Exception: pass
        if interview_time:
            try:
                h, mn = interview_time.split(":")
                due_time_val = time_cls(int(h), int(mn))
            except Exception: pass

        desc = f"📍 Место: {place}" if place else None
        await get_task_service().create_task(TaskCreate(
            title=f"Собеседование: {c.name}",
            description=desc,
            due_date=due_date,
            due_time=due_time_val,
            priority="high",
            category="Подбор персонала",
        ), created_by="admin")

        summary = " ".join(filter(None, [interview_date, interview_time, place]))
        return f"✅ Подтверждено!\nКандидат <b>{c.name}</b> переведён на «Собеседование».\n{summary}"
    finally:
        db.close()


# ── Callback: ✅ Подтвердить ───────────────────────────────────────────────

async def handle_confirm_callback(update, context):
    query = update.callback_query
    await query.answer()
    candidate_id = int(query.data.split("_")[-1])

    result = await _finalize_interview(candidate_id)
    await query.edit_message_text(result, parse_mode="HTML")


# ── Callback: ✏️ Другое — начало ConversationHandler ─────────────────────

async def handle_other_callback(update, context):
    query = update.callback_query
    await query.answer()
    candidate_id = int(query.data.split("_")[-1])

    context.user_data["interview_instruction_candidate"] = candidate_id

    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate
    db = SessionLocal()
    try:
        c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        name = c.name if c else f"#{candidate_id}"
        date = c.pending_interview_date or "не указана"
        time_s = c.pending_interview_time or "не указано"
        place = c.pending_interview_place or "не указано"
    finally:
        db.close()

    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(
        f"✏️ <b>Напишите инструкцию для кандидата {name}</b>\n"
        f"Текущее время: {date} {time_s}, место: {place}\n\n"
        f"Примеры:\n"
        f"• «предложи в пятницу в 17:00»\n"
        f"• «да, но только Гранд Палас»\n"
        f"• «скажи что позвоним завтра»\n\n"
        f"/cancel — отменить",
        parse_mode="HTML"
    )
    return INSTRUCTION_WAITING


# ── State INSTRUCTION_WAITING: получаем свободный текст ──────────────────

async def handle_instruction_text(update, context):
    candidate_id = context.user_data.pop("interview_instruction_candidate", None)
    if not candidate_id:
        return ConversationHandler.END

    instruction = update.message.text.strip()
    await update.message.reply_text("⏳ Обрабатываю...")

    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate, TelegramMessage
    from app.services.config_service import ConfigService
    from app.services.notify import send_secretary_message
    from app.services.task_service import get_task_service
    from app.schemas.task import TaskCreate

    db = SessionLocal()
    try:
        c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not c:
            await update.message.reply_text("❌ Кандидат не найден.")
            return ConversationHandler.END

        cfg = ConfigService().load()
        from app.services.llm_client import chat, get_client
        if not get_client(cfg):
            await update.message.reply_text("❌ API key не настроен.")
            return ConversationHandler.END

        today_str = date_cls.today().isoformat()
        prompt = (
            f"Сегодня {today_str}.\n"
            f"Ты ассистент HR-менеджера. Менеджер дал инструкцию по кандидату.\n\n"
            f"Кандидат: {c.name}\n"
            f"Текущие согласованные данные: {c.pending_interview_date or '?'} {c.pending_interview_time or ''}, место: {c.pending_interview_place or 'не указано'}\n\n"
            f"Инструкция менеджера: «{instruction}»\n\n"
            "Определи что написать кандидату, руководствуясь этими правилами:\n"
            "— Если менеджер МЕНЯЕТ дату/время/место (пересогласование): напиши вежливое сообщение-запрос.\n"
            "  Формат: 'К сожалению, [старое время/место] не получится. Удобно ли вам [новые условия]?'\n"
            "  НЕ пиши подтверждение — кандидат ещё не согласился на новые условия.\n"
            "— Если менеджер ПОДТВЕРЖДАЕТ текущие условия: напиши финальное подтверждение.\n"
            "— Если менеджер просит передать инфо или перезвонить: напиши соответствующее сообщение.\n"
            "— Стиль: нейтрально-деловой, вежливый. Без восклицательного энтузиазма и неформальных фраз.\n\n"
            "Дополнительно определи:\n"
            "— Нужна ли задача-напоминание менеджеру (перезвонить, связаться и т.п.)\n"
            "— Если нужно обновить дату/время/место — укажи новые значения\n\n"
            "Ответь ТОЛЬКО в JSON (без markdown):\n"
            '{"message_to_candidate": "текст", '
            '"create_task": true/false, '
            '"task_title": "заголовок или null", '
            '"task_due_date": "YYYY-MM-DD или null", '
            '"task_due_time": "HH:MM или null", '
            '"new_date": "YYYY-MM-DD или null", '
            '"new_time": "HH:MM или null", '
            '"new_place": "место или null"}'
        )

        raw = chat(cfg, [{"role": "user", "content": prompt}], max_tokens=600)
        if not raw:
            await update.message.reply_text("❌ Не удалось получить ответ AI.")
            return ConversationHandler.END

        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            await update.message.reply_text("❌ Не удалось разобрать ответ AI.")
            return ConversationHandler.END

        data = json.loads(m.group())

        # Обновить pending данные если Claude предложил новые
        if data.get("new_date"):
            c.pending_interview_date = data["new_date"]
        if data.get("new_time"):
            c.pending_interview_time = data["new_time"]
        if data.get("new_place"):
            c.pending_interview_place = data["new_place"]
        db.commit()

        # Отправить сообщение кандидату
        msg_to_cand = (data.get("message_to_candidate") or "").strip()
        sent_cand = False
        if msg_to_cand and c.telegram_chat_id:
            err = await send_secretary_message(c.telegram_chat_id, msg_to_cand)
            if not err:
                out = TelegramMessage(candidate_id=candidate_id, direction="out",
                                      text=msg_to_cand, sent_by_ai=1)
                db.add(out)
                db.commit()
                sent_cand = True

        # Создать задачу если нужно
        task_created = False
        if data.get("create_task"):
            try:
                due_date = None
                due_time_val = None
                if data.get("task_due_date"):
                    try: due_date = date_cls.fromisoformat(data["task_due_date"])
                    except Exception: pass
                if data.get("task_due_time"):
                    try:
                        h, mn = data["task_due_time"].split(":")
                        due_time_val = time_cls(int(h), int(mn))
                    except Exception: pass

                await get_task_service().create_task(TaskCreate(
                    title=data.get("task_title") or f"Связаться с кандидатом: {c.name}",
                    description=f"Инструкция: «{instruction}»",
                    due_date=due_date,
                    due_time=due_time_val,
                    priority="medium",
                    category="Подбор персонала",
                ), created_by="admin")
                task_created = True
            except Exception as e:
                log.warning("Failed to create task from instruction: %s", e)

        # Сводка для менеджера
        reply_parts = []
        if sent_cand:
            reply_parts.append(f"✉️ Отправлено кандидату:\n<i>{msg_to_cand[:300]}</i>")
        if task_created:
            reply_parts.append("✅ Задача создана в трекере.")

        new_summary = " ".join(filter(None, [
            c.pending_interview_date, c.pending_interview_time, c.pending_interview_place
        ]))
        if new_summary:
            reply_parts.append(f"📌 Текущие детали: {new_summary}")

        await update.message.reply_text(
            "\n\n".join(reply_parts) or "✅ Выполнено.",
            parse_mode="HTML"
        )
    finally:
        db.close()

    return ConversationHandler.END


async def cancel_instruction(update, context):
    context.user_data.pop("interview_instruction_candidate", None)
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END


async def handle_instruction_timeout(update, context):
    context.user_data.pop("interview_instruction_candidate", None)
    if update.message:
        await update.message.reply_text(
            "⏰ Время вышло. Инструкция отменена — нажмите «✏️ Другое» снова."
        )
    return ConversationHandler.END


def build_interview_decision_handlers():
    """Returns list of handlers to register in application."""
    confirm_handler = CallbackQueryHandler(handle_confirm_callback, pattern=r'^iview_ok_\d+$')

    other_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_other_callback, pattern=r'^iview_other_\d+$')],
        states={
            INSTRUCTION_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_instruction_text)
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, handle_instruction_timeout)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_instruction)],
        per_chat=True,
        allow_reentry=True,
        conversation_timeout=300,
    )
    return [confirm_handler, other_conv]
