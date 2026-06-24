"""Proactive follow-up for candidates who go silent during 'общение' stage."""
import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# Dedup so a candidate stuck on a misconfigured (blank message) strategy
# doesn't get re-notified about it every 15 minutes.
_missing_msg_notified: set[tuple[int, int]] = set()


async def run_follow_up_check():
    """Called every 15 min by job_queue. Checks all 'общение' candidates.

    Each candidate's vacancy may have its own HiringStrategy with its own
    follow_up_enabled/delay/messages — resolved per-candidate, not once
    globally, since different vacancies can run different strategies.
    """
    from sqlalchemy import or_
    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate, Vacancy
    from app.services.config_service import ConfigService
    from app.services.work_hours import is_working_now
    from app.services.strategy_resolver import get_strategy

    cfg = ConfigService().load()
    if not is_working_now(cfg):
        return

    now_utc = datetime.utcnow()

    db = SessionLocal()
    try:
        candidates = db.query(Candidate).filter(
            Candidate.stage == "общение",
            Candidate.telegram_chat_id.isnot(None),
            Candidate.telegram_chat_id != "",
            Candidate.is_paused != True,
            Candidate.pending_interview_date.is_(None),  # уже назначено — не трогаем
            # интервью завершено — нечего напоминать (NULL = старые записи без фазы, не трогаем их)
            or_(Candidate.interview_phase.is_(None), Candidate.interview_phase != "done"),
        ).all()

        for c in candidates:
            try:
                vacancy = db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first() if c.vacancy_id else None
                strategy = get_strategy(db, vacancy)

                # Follow-up is configured solely on the HiringStrategy now —
                # no vacancy strategy means no follow-up for that candidate.
                if strategy is None or not strategy.follow_up_enabled:
                    continue
                delay = timedelta(hours=float(strategy.follow_up_delay_hours or 1))
                msg_1 = (strategy.follow_up_message_1 or "").strip()
                msg_2 = (strategy.follow_up_message_2 or "").strip()
                decline_after_hours = strategy.decline_after_hours

                await _process(c, db, delay, now_utc, msg_1, msg_2, decline_after_hours)
            except Exception as e:
                log.warning("follow_up: error for candidate_id=%s: %s", c.id, e)
    finally:
        db.close()


async def _process(c, db, delay: timedelta, now_utc: datetime, msg_1: str, msg_2: str,
                    decline_after_hours):
    from app.models.recruitment import TelegramMessage
    from app.services.notify import send_secretary_message, send_notification

    count = c.follow_up_count or 0

    # The candidate already has a real, specific question sitting unanswered
    # (the AI deferred it to the admin) — nudging them with a generic "still
    # interested?" message instead of an actual answer is exactly the
    # confusing non-response that caused this in the first place. Wait for
    # the admin to reply rather than competing with that promise.
    if c.pending_question:
        return

    if count >= 3:
        # Follow-ups exhausted. If the strategy allows decline-suggestion and
        # enough time has passed since the last follow-up with no reply,
        # flag it for the admin — never auto-decline.
        if decline_after_hours and not c.pending_decline_suggested_at:
            reference = c.follow_up_last_sent_at
            if reference and now_utc - reference >= timedelta(hours=float(decline_after_hours)):
                c.pending_decline_suggested_at = now_utc
                db.commit()
                await send_notification(
                    f"🔕 <b>Предложение отказа</b>\n"
                    f"Кандидат <b>{c.name}</b> не отвечает уже более {decline_after_hours}ч после напоминаний.\n"
                    f"Решение принимаете вы — откройте карточку кандидата, чтобы отказать или продолжить ждать."
                )
                log.info("follow_up: decline suggested for candidate_id=%s", c.id)
        return

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
        msg_text = msg_1 if count == 0 else msg_2
        if not msg_text:
            key = (c.id, count)
            if key not in _missing_msg_notified:
                _missing_msg_notified.add(key)
                log.warning("follow_up: no message text configured for candidate_id=%s (count=%d)", c.id, count)
                await send_notification(
                    f"⚠️ <b>Нет текста напоминания</b>\nУ стратегии найма кандидата <b>{c.name}</b> "
                    f"включены напоминания, но не заполнен текст сообщения №{count + 1}. Заполните его в стратегии."
                )
            return

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
