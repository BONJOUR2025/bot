"""Proactive follow-up for candidates who go silent during 'общение' stage."""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
WINDOW_START = 10  # 10:00 МСК
WINDOW_END = 20    # 20:00 МСК

DEFAULT_MSG_1 = "Здравствуйте! Остались ли у вас вопросы по вакансии? Готовы записаться на собеседование?"
DEFAULT_MSG_2 = "Мы всё ещё ждём вашего ответа. Если вас интересует вакансия — напишите, будем рады помочь."


def _now_msk() -> datetime:
    return datetime.now(MOSCOW_TZ)


def _is_in_window() -> bool:
    return WINDOW_START <= _now_msk().hour < WINDOW_END


async def run_follow_up_check():
    """Called every 15 min by job_queue. Checks all 'общение' candidates."""
    if not _is_in_window():
        return

    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate
    from app.services.config_service import ConfigService

    cfg = ConfigService().load()
    if not cfg.get("follow_up_enabled"):
        return

    delay_hours = float(cfg.get("follow_up_delay_hours") or 1)
    delay = timedelta(hours=delay_hours)
    now_utc = datetime.utcnow()

    db = SessionLocal()
    try:
        candidates = db.query(Candidate).filter(
            Candidate.stage == "общение",
            Candidate.telegram_chat_id.isnot(None),
            Candidate.telegram_chat_id != "",
            Candidate.is_paused != True,
            Candidate.pending_interview_date.is_(None),  # уже назначено — не трогаем
        ).all()

        for c in candidates:
            try:
                await _process(c, db, cfg, delay, now_utc)
            except Exception as e:
                log.warning("follow_up: error for candidate_id=%s: %s", c.id, e)
    finally:
        db.close()


async def _process(c, db, cfg, delay: timedelta, now_utc: datetime):
    from app.models.recruitment import TelegramMessage
    from app.services.notify import send_secretary_message, send_notification

    count = c.follow_up_count or 0

    if count >= 3:
        return  # уже уведомили, больше не трогаем

    if count == 0:
        # Отсчёт от последнего входящего сообщения кандидата
        last_in = db.query(TelegramMessage).filter(
            TelegramMessage.candidate_id == c.id,
            TelegramMessage.direction == "in",
        ).order_by(TelegramMessage.created_at.desc()).first()

        if not last_in:
            return
        reference = last_in.created_at
    else:
        # Отсчёт от времени предыдущего follow-up
        reference = c.follow_up_last_sent_at
        if not reference:
            return

    if now_utc - reference < delay:
        return  # ещё рано

    if count < 2:
        msg_key = "follow_up_message_1" if count == 0 else "follow_up_message_2"
        default = DEFAULT_MSG_1 if count == 0 else DEFAULT_MSG_2
        msg_text = (cfg.get(msg_key) or "").strip() or default

        # Race condition check: re-query to see if a new "in" message arrived after reference
        last_in_recheck = db.query(TelegramMessage).filter(
            TelegramMessage.candidate_id == c.id,
            TelegramMessage.direction == "in",
        ).order_by(TelegramMessage.created_at.desc()).first()
        if last_in_recheck and last_in_recheck.created_at > reference:
            log.info("follow_up: candidate_id=%s replied after reference, skipping follow-up", c.id)
            c.follow_up_count = 0
            db.commit()
            return

        err = await send_secretary_message(c.telegram_chat_id, msg_text)
        if err:
            log.warning("follow_up: send failed candidate_id=%s: %s", c.id, err)
            return

        tg_msg = TelegramMessage(
            candidate_id=c.id,
            direction="out",
            text=msg_text,
            sent_by_ai=1,
        )
        db.add(tg_msg)
        c.follow_up_count = count + 1
        c.follow_up_last_sent_at = now_utc
        db.commit()
        log.info("follow_up #%d sent to candidate_id=%s", count + 1, c.id)

    else:
        # count == 2: обе попытки исчерпаны → уведомляем
        await send_notification(
            f"😶 <b>Кандидат не выходит на связь</b>\n"
            f"Кандидат <b>{c.name}</b> не ответил после двух напоминаний.\n"
            f"Рекомендуем связаться вручную или закрыть диалог."
        )
        c.follow_up_count = 3
        c.follow_up_last_sent_at = now_utc
        db.commit()
        log.info("follow_up: admin notified about silent candidate_id=%s", c.id)
