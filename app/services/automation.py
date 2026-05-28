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


def matches_filters(candidate, cfg: dict) -> bool:
    """Check if candidate matches automation filters (flat config keys)."""
    if not cfg:
        return True

    age_min = cfg.get("automation_age_min")
    age_max = cfg.get("automation_age_max")
    sources_str = cfg.get("automation_sources_str", "")

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

        if not force and not matches_filters(c, cfg):
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
            message = (
                f"{name_short}, здравствуйте! Для удобного общения приглашаем вас в Telegram.\n\n"
                f"Пожалуйста, перейдите по ссылке и нажмите «Отправить» — это займёт 5 секунд:\n"
                f"{tg_link}\n\n"
                f"⚠️ Важно: не изменяйте текст сообщения — это нужно для автоматической идентификации."
            )
        else:
            message = (
                f"{name_short}, здравствуйте! Для удобного общения напишите нам в Telegram: "
                f"@{personal_username or 'наш менеджер'}.\n"
                f"При написании укажите код: {code}"
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
