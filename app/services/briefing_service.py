"""Daily 10:00 MSK morning briefing."""
import logging
from datetime import datetime, timedelta, date as date_cls

log = logging.getLogger(__name__)


async def send_morning_briefing():
    """Gather tasks, interviews, unread messages; summarize important ones; send to admin."""
    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate, TelegramMessage
    from app.services.config_service import ConfigService
    from app.services.task_service import get_task_service
    from app.services.notify import send_notification

    cfg = ConfigService().load()
    today = date_cls.today()
    yesterday_iso = str(today - timedelta(days=1))
    tomorrow_iso = str(today + timedelta(days=1))
    now_utc = datetime.utcnow()
    since_utc = now_utc - timedelta(hours=24)

    db = SessionLocal()
    try:
        task_svc = get_task_service()

        overdue   = await task_svc.list_tasks(due_to=yesterday_iso, include_done=False)
        overdue   = [t for t in overdue if t.status != "done"]
        today_t   = await task_svc.list_tasks(due_date=str(today), include_done=False)
        today_t   = [t for t in today_t if t.status != "done"]
        tomorrow_t = await task_svc.list_tasks(due_date=tomorrow_iso, include_done=False)
        in_prog   = await task_svc.list_tasks(status="in_progress")

        interviews = db.query(Candidate).filter(Candidate.stage == "собеседование").all()

        unread_tg = (
            db.query(TelegramMessage)
            .filter(
                TelegramMessage.direction == "in",
                TelegramMessage.created_at >= since_utc,
            )
            .order_by(TelegramMessage.created_at.asc())
            .limit(60)
            .all()
        )
        # Load candidate names for TG messages
        cand_names = {}
        for m in unread_tg:
            if m.candidate_id not in cand_names:
                c = db.query(Candidate).filter(Candidate.id == m.candidate_id).first()
                cand_names[m.candidate_id] = c.name if c else f"#{m.candidate_id}"

        unread_hh = db.query(Candidate).filter(
            Candidate.has_unread_hh_msg == 1
        ).all()

    finally:
        db.close()

    # ── Блок задач ──────────────────────────────────────────────────────────
    task_lines = []

    if overdue:
        task_lines.append(f"🔴 <b>Просрочено ({len(overdue)}):</b>")
        for t in overdue[:5]:
            task_lines.append(f"  • {t.title}" + (f" ({t.due_date})" if t.due_date else ""))

    if today_t:
        task_lines.append(f"📌 <b>Сегодня ({len(today_t)}):</b>")
        for t in today_t[:5]:
            ts = str(t.due_time)[:5] if t.due_time else ""
            task_lines.append(f"  • {t.title}" + (f" в {ts}" if ts else ""))

    if tomorrow_t:
        task_lines.append(f"📋 <b>Завтра ({len(tomorrow_t)}):</b>")
        for t in tomorrow_t[:3]:
            task_lines.append(f"  • {t.title}")

    if in_prog:
        task_lines.append(f"⚙️ <b>В работе ({len(in_prog)}):</b>")
        for t in in_prog[:3]:
            task_lines.append(f"  • {t.title}")

    # ── Блок собеседований ──────────────────────────────────────────────────
    interview_lines = []
    if interviews:
        interview_lines.append(f"👥 <b>На этапе «Собеседование» ({len(interviews)}):</b>")
        for c in interviews[:5]:
            interview_lines.append(f"  • {c.name}")

    # ── Блок важных сообщений ───────────────────────────────────────────────
    msg_summary = await _summarize_messages(unread_tg, cand_names, unread_hh, cfg)

    # ── Финальный текст ─────────────────────────────────────────────────────
    sections = [f"🌅 <b>Доброе утро! Сводка на {today.strftime('%d.%m.%Y')}</b>"]

    if task_lines:
        sections.append("\n".join(task_lines))
    else:
        sections.append("✅ Задач на сегодня нет")

    if interview_lines:
        sections.append("\n".join(interview_lines))

    if msg_summary:
        sections.append(f"💬 <b>Требует внимания:</b>\n{msg_summary}")

    await send_notification("\n\n".join(sections))
    log.info("Morning briefing sent")


async def _summarize_messages(tg_msgs, cand_names: dict, hh_candidates, cfg) -> str:
    """Use Claude to extract only important/actionable messages."""
    if not tg_msgs and not hh_candidates:
        return ""

    api_key = (cfg.get("anthropic_api_key") or "").strip() or None
    if not api_key:
        # Fallback without Claude
        parts = []
        if tg_msgs:
            parts.append(f"• {len(tg_msgs)} новых сообщений от кандидатов в Telegram")
        if hh_candidates:
            names = ", ".join(c.name for c in hh_candidates[:5])
            parts.append(f"• Непрочитанные на hh.ru: {names}")
        return "\n".join(parts)

    # Строим контекст для Claude
    lines = []
    if tg_msgs:
        lines.append("Telegram — входящие от кандидатов за 24ч:")
        for m in tg_msgs[:40]:
            name = cand_names.get(m.candidate_id, "?")
            lines.append(f"  [{name}]: {m.text[:120]}")

    if hh_candidates:
        lines.append("\nhh.ru — непрочитанные:")
        for c in hh_candidates[:10]:
            lines.append(f"  • {c.name} (вакансия #{c.vacancy_id})")

    context_text = "\n".join(lines)

    proxy_url = None
    try:
        from app.settings import settings as _s
        proxy_url = getattr(_s, "telegram_proxy", None)
    except Exception:
        pass
    http_client = None
    if proxy_url:
        import httpx
        http_client = httpx.Client(proxy=proxy_url)

    from anthropic import Anthropic
    client = Anthropic(api_key=api_key, http_client=http_client)

    prompt = (
        "Ты помощник HR-менеджера. Проанализируй входящие сообщения за последние 24ч.\n"
        "Выдели ТОЛЬКО важное и требующее действий:\n"
        "— вопросы без ответа\n"
        "— готовность к собеседованию\n"
        "— негатив или отказ\n"
        "— срочные запросы\n\n"
        "Пропусти: приветствия, 'спасибо', нейтральные 'ok', уже решённые вопросы.\n"
        "Если важного нет — ответь одним словом: NONE\n"
        "Иначе — максимум 5 пунктов, каждый с именем кандидата.\n\n"
        f"{context_text}"
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.content[0].text.strip()
        return "" if result.upper() == "NONE" else result
    except Exception as e:
        log.warning("briefing: Claude summarize failed: %s", e)
        return ""
