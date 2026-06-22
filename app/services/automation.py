"""Candidate automation pipeline."""
import asyncio
import logging
from datetime import datetime

log = logging.getLogger(__name__)

# In-memory toggle — always False on restart
_enabled: bool = False


def is_enabled() -> bool:
    return _enabled


def set_enabled(val: bool) -> None:
    global _enabled
    _enabled = val


def matches_filters(candidate, cfg: dict, strategy=None) -> bool:
    """Check if candidate matches automation filters.

    If the candidate's vacancy has a HiringStrategy assigned, the strategy's
    filters are authoritative and global config filters are ignored —
    there is no dual-path fallback once a strategy is set.
    """
    if strategy is not None:
        age_min, age_max, sources_str = strategy.age_min, strategy.age_max, strategy.sources_str or ""
    elif cfg:
        age_min = cfg.get("automation_age_min")
        age_max = cfg.get("automation_age_max")
        sources_str = cfg.get("automation_sources_str", "")
    else:
        return True

    # Age range
    try:
        if age_min and candidate.age and int(candidate.age) < int(age_min):
            return False
    except (TypeError, ValueError):
        pass
    try:
        if age_max and candidate.age and int(candidate.age) > int(age_max):
            return False
    except (TypeError, ValueError):
        pass

    # Sources filter
    if sources_str:
        sources = [s.strip() for s in sources_str.split(",") if s.strip()]
        if sources and candidate.source not in sources:
            return False

    return True


async def trigger_for_candidate(candidate_id: int, force: bool = False) -> str:
    """
    Run automation for one candidate.
    force=True bypasses global toggle (used for test runs).
    Returns status string.
    """
    if not force and not _enabled:
        return "skipped: automation disabled"

    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate, RecruitmentSource
    from app.services.config_service import ConfigService
    from app.services import hh_api
    import secrets
    import string
    from urllib.parse import quote

    db = SessionLocal()
    try:
        c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not c:
            return "not found"

        cfg = ConfigService().load()

        from app.models.recruitment import Vacancy
        from app.services.strategy_resolver import get_strategy
        vacancy = db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first() if c.vacancy_id else None
        strategy = get_strategy(db, vacancy)

        if not force and not matches_filters(c, cfg, strategy):
            return "skipped: filters not matched"

        # Only for hh candidates that have external_id
        if c.source != "hh" or not c.external_id:
            return "skipped: not an hh candidate"

        # Generate TG link code if not exists
        if not getattr(c, "telegram_link_code", None):
            alphabet = string.ascii_uppercase + string.digits
            token = "".join(secrets.choice(alphabet) for _ in range(6))
            code = f"CAND-{c.id}-{token}"
            try:
                c.telegram_link_code = code
                db.commit()
            except Exception:
                code = f"CAND-{c.id}-NOCODE"
        else:
            code = c.telegram_link_code

        personal_username = (cfg.get("tg_personal_username") or "").strip().lstrip("@")
        if personal_username:
            tg_link = f"https://t.me/{personal_username}?text={quote(code)}"
            link_text = tg_link
        else:
            tg_link = None
            link_text = f"Код для привязки: {code}"

        # Build message
        name_short = c.name.split()[0] if c.name else "Здравствуйте"
        if tg_link:
            default_tpl = (
                "{name}, здравствуйте! Для удобного общения приглашаем вас в Telegram.\n\n"
                "Пожалуйста, перейдите по ссылке и нажмите «Отправить» — это займёт 5 секунд:\n"
                "{link}\n\n"
                "⚠️ Важно: не изменяйте текст сообщения — это нужно для автоматической идентификации."
            )
            tpl = (
                (strategy.hh_message_with_link if strategy else None)
                or cfg.get("automation_hh_message_with_link") or ""
            ).strip() or default_tpl
            message = tpl.format(name=name_short, link=tg_link, code=code)
        else:
            default_tpl = (
                "{name}, здравствуйте! Для удобного общения напишите нам в Telegram: "
                "@{username}.\nПри написании укажите код: {code}"
            )
            tpl = (
                (strategy.hh_message_no_link if strategy else None)
                or cfg.get("automation_hh_message_no_link") or ""
            ).strip() or default_tpl
            message = tpl.format(
                name=name_short,
                code=code,
                username=personal_username or "наш менеджер",
                link=link_text,
            )

        # Send hh message
        src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "hh").first()
        if not src or not src.access_token:
            return "error: hh not connected"

        try:
            await hh_api.send_message(src.access_token, c.external_id, message)
        except Exception as e:
            log.warning("Automation: hh send_message failed for candidate %s: %s", c.id, e)
            return f"error: hh send failed: {e}"

        # Move to "ждем_привязки"
        c.stage = "ждем_привязки"
        c.updated_at = datetime.utcnow()
        db.commit()
        log.info("Automation triggered for candidate_id=%s", c.id)
        return "ok"
    finally:
        db.close()
