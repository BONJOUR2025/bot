"""Background sync: pulls new candidates from hh.ru and Avito into the CRM."""
import asyncio
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None
_DEFAULT_INTERVAL = 15 * 60  # fallback 15 min; actual per-source interval used inside loop

# Stages considered "active" for message polling
_ACTIVE_STAGES = {"отклик", "собеседование", "ждем"}


async def _sync_once() -> None:
    from app.db.session import SessionLocal
    from app.models.recruitment import RecruitmentSource, VacancyLink, Candidate
    from app.services import hh_api, avito_api

    db = SessionLocal()
    try:
        sources = db.query(RecruitmentSource).filter(RecruitmentSource.is_active == True).all()
        for src in sources:
            links = db.query(VacancyLink).filter(
                VacancyLink.source_id == src.id,
                VacancyLink.sync_enabled == True,
            ).all()
            if not links:
                continue

            token = src.access_token
            if src.source == "avito" and src.client_id and src.client_secret:
                try:
                    tok_data = await avito_api.get_token(src.client_id, src.client_secret)
                    token = tok_data["access_token"]
                    src.access_token = token
                    db.commit()
                except Exception as e:
                    logger.warning(f"[Sync] Avito token refresh failed: {e}")
                    continue
            elif src.source == "hh":
                token = await _refresh_hh_token_if_needed(db, src) or token

            for link in links:
                try:
                    new_candidates = await _sync_link(db, src, link, token)
                    new_count = len(new_candidates)
                    link.last_synced_at = datetime.utcnow()
                    link.last_sync_count = new_count
                    src.last_error = ""
                    db.commit()
                    if new_count:
                        logger.info(f"[Sync] {src.source} vacancy={link.external_vacancy_id}: +{new_count} candidates")
                        await _notify_new_candidates(src.source, link, new_candidates)
                except Exception as e:
                    logger.warning(f"[Sync] {src.source} link {link.id} error: {e}")
                    src.last_error = str(e)
                    db.commit()

            # Poll hh.ru messages for active candidates
            if src.source == "hh" and token:
                try:
                    await _check_hh_messages(db, src, token)
                except Exception as e:
                    logger.warning(f"[Sync] hh message check failed: {e}")

        # Check 24h unlinked candidates
        try:
            await _check_pending_tg_links(db)
        except Exception as e:
            logger.warning(f"[Sync] pending TG check error: {e}")
    finally:
        db.close()


# Refresh this far ahead of the recorded expiry. hh access tokens live ~14 days,
# so a 1-day margin means a normally-running sync always renews well before the
# token dies, and a box that was off for a few days still recovers on first run.
_HH_REFRESH_MARGIN = timedelta(days=1)

# Re-notify guard: without it a source whose refresh_token is genuinely dead
# (needs manual re-auth) would alert on every single sync cycle.
_hh_refresh_failure_notified = False


async def _refresh_hh_token_if_needed(db, src) -> str | None:
    """Renew the hh access token before it expires, returning the token to use.

    hh_api.refresh_access_token() existed from the start but was never called
    anywhere — so the token simply died every ~2 weeks and the whole hh
    integration went silent (found in production as a 403 on every sync, with
    a token that had expired a month earlier and nobody noticed). Returns None
    if nothing was refreshed, so the caller keeps the existing token.
    """
    global _hh_refresh_failure_notified
    from app.services import hh_api
    from app.services.notify import send_notification

    if not src.refresh_token:
        return None
    expires_at = src.token_expires_at
    if expires_at and expires_at - _HH_REFRESH_MARGIN > datetime.utcnow():
        return None  # still comfortably valid

    try:
        data = await hh_api.refresh_access_token(
            src.client_id or "", src.client_secret or "", src.refresh_token
        )
    except Exception as e:
        logger.warning("[Sync] hh token refresh failed: %s", e)
        src.last_error = f"Не удалось обновить токен hh.ru: {e}"
        db.commit()
        if not _hh_refresh_failure_notified:
            _hh_refresh_failure_notified = True
            await send_notification(
                "🔑 <b>hh.ru: не удалось обновить токен</b>\n"
                "Отклики с hh.ru не загружаются. Переподключите hh.ru в разделе «Подбор» "
                f"— требуется повторная авторизация.\n\nОшибка: {e}"
            )
        return None

    _hh_refresh_failure_notified = False
    token = data.get("access_token")
    if not token:
        return None
    src.access_token = token
    # hh rotates the refresh token on every use — keeping the old one would
    # make the *next* refresh fail with an already-used token.
    if data.get("refresh_token"):
        src.refresh_token = data["refresh_token"]
    if data.get("expires_in"):
        src.token_expires_at = datetime.utcnow() + timedelta(seconds=int(data["expires_in"]))
    src.last_error = ""
    db.commit()
    logger.info("[Sync] hh token refreshed, valid until %s", src.token_expires_at)
    return token


async def _check_pending_tg_links(db) -> None:
    """Notify admin about candidates waiting for TG link more than 24h."""
    from app.models.recruitment import Candidate
    from app.services.notify import send_notification

    cutoff = datetime.utcnow() - timedelta(hours=24)
    pending = db.query(Candidate).filter(
        Candidate.stage == "ждем_привязки",
        Candidate.updated_at <= cutoff,
        Candidate.telegram_chat_id == None,
    ).all()

    for c in pending:
        # Only notify once — use last_error as flag
        if c.last_error == "tg_notified":
            continue
        await send_notification(
            f"⏰ <b>TG не привязан 24ч</b>\n"
            f"Кандидат <b>{c.name}</b> не перешёл по ссылке в течение 24 часов.\n"
            f"Вакансия: {c.vacancy.title if c.vacancy else '?'}"
        )
        c.last_error = "tg_notified"
        db.commit()


async def _notify_new_candidates(source: str, link, candidates: list[dict]) -> None:
    from app.services.notify import send_notification
    src_label = "hh.ru" if source == "hh" else "Авито"
    vac_title = (getattr(link, "external_vacancy_title", "") or "") or \
                (link.vacancy.title if getattr(link, "vacancy", None) else "") or \
                f"#{link.external_vacancy_id}"
    count = len(candidates)
    word = "кандидат" if count == 1 else "кандидата" if count < 5 else "кандидатов"
    lines = [f"👤 <b>Новые отклики ({src_label})</b>\n{vac_title}: +{count} {word}\n"]
    for c in candidates:
        age_str = f", {c['age']} лет" if c.get("age") else ""
        phone_str = f"\n📞 {c['phone']}" if c.get("phone") else ""
        resume_str = f"\n🔗 <a href=\"{c['resume_url']}\">Резюме</a>" if c.get("resume_url") else ""
        lines.append(f"• <b>{c['name']}</b>{age_str}{phone_str}{resume_str}")
    await send_notification("\n".join(lines))


async def _check_hh_messages(db, src, token: str) -> None:
    """Poll hh.ru messages for active candidates, notify on new applicant messages."""
    from app.models.recruitment import Candidate
    from app.services import hh_api
    from app.services.notify import send_notification
    from app.db.session import SessionLocal

    cutoff = datetime.utcnow() - timedelta(days=60)
    candidates = db.query(Candidate).filter(
        Candidate.source == "hh",
        Candidate.external_id.isnot(None),
        Candidate.stage.in_(_ACTIVE_STAGES),
        Candidate.created_at >= cutoff,
    ).all()

    logger.info("[Sync] hh message check: %d active candidates to poll", len(candidates))

    sem = asyncio.Semaphore(3)

    async def check_one(cand_id: int, neg_id: str, name: str, last_id: str | None) -> None:
        async with sem:
            try:
                messages = await hh_api.get_messages(token, neg_id)
                logger.info("[Sync] hh messages neg=%s candidate=%s: %d messages, last_msg_id=%r",
                            neg_id, name, len(messages), last_id)
                if not messages:
                    return
                latest = max(messages, key=lambda m: m["created_at"])
                latest_id = latest["id"]
                latest_type = latest["author_type"]
                logger.info("[Sync] hh latest msg: id=%s type=%s text=%r",
                            latest_id, latest_type, latest["text"][:60])

                # Update last_msg_id in its own session to avoid concurrency issues
                own_db = SessionLocal()
                try:
                    c = own_db.query(Candidate).filter(Candidate.id == cand_id).first()
                    if not c:
                        return
                    if latest_type != "applicant":
                        c.last_msg_id = latest_id
                        own_db.commit()
                        return
                    if c.last_msg_id == latest_id:
                        logger.debug("[Sync] hh msg already seen: %s", latest_id)
                        return
                    # New message from applicant — save ID before notifying
                    c.last_msg_id = latest_id
                    own_db.commit()
                finally:
                    own_db.close()

                msg_text = latest["text"].strip()
                if not msg_text:
                    logger.info("[Sync] hh new applicant message from %s has empty text, skipping notification", name)
                    return

                logger.warning("[Sync] hh NEW applicant message from %s (neg=%s), attempting notification", name, neg_id)
                ok = await send_notification(
                    f"💬 <b>Новое сообщение от кандидата (hh.ru)</b>\n"
                    f"<b>{name}</b>: {msg_text[:200]}"
                )
                if ok:
                    logger.info("[Sync] hh notification sent for %s", name)
                else:
                    logger.warning("[Sync] hh notification FAILED for %s — check notification_chat_id and bot token", name)
            except Exception as exc:
                logger.warning("[Sync] hh message check failed for neg=%s (%s): %s", neg_id, name, exc)

    await asyncio.gather(*[
        check_one(c.id, c.external_id, c.name, c.last_msg_id)
        for c in candidates
    ])


async def _sync_link(db, src, link, token: str) -> list[dict]:
    from app.models.recruitment import Candidate
    from app.services import hh_api, avito_api

    if src.source == "hh":
        new_items = await _collect_hh(token, link.external_vacancy_id)
    elif src.source == "avito":
        new_items = await avito_api.get_applications_for_vacancy(token, src.employer_id, link.external_vacancy_id)
    else:
        return []

    new_candidates = []
    new_candidate_objs = []
    for item in new_items:
        ext_id = item["external_id"]
        exists = db.query(Candidate).filter(
            Candidate.vacancy_id == link.vacancy_id,
            Candidate.source == src.source,
            Candidate.external_id == ext_id,
        ).first()
        if not exists:
            applied_at = None
            raw_applied = item.get("applied_at")
            if raw_applied:
                try:
                    applied_at = datetime.fromisoformat(raw_applied.replace("Z", "+00:00"))
                except Exception:
                    pass

            c = Candidate(
                vacancy_id=link.vacancy_id,
                name=item["name"],
                phone=item.get("phone", ""),
                email=item.get("email", ""),
                source=src.source,
                external_id=ext_id,
                resume_url=item.get("resume_url", ""),
                photo_url=item.get("photo_url", ""),
                age=item.get("age"),
                stage="отклик",
                notes=item.get("notes", ""),
                created_at=applied_at or datetime.utcnow(),
            )
            db.add(c)
            new_candidates.append({
                "name": item["name"],
                "age": item.get("age"),
                "phone": item.get("phone", ""),
                "resume_url": item.get("resume_url", ""),
            })
            new_candidate_objs.append(c)
    db.flush()

    # Trigger automation for newly added candidates — trigger_for_candidate
    # resolves the vacancy's strategy and applies its filters itself, so no
    # pre-filtering is needed here.
    from app.services.automation import is_enabled, trigger_for_candidate
    if is_enabled() and new_candidate_objs:
        for cand_obj in new_candidate_objs:
            asyncio.ensure_future(trigger_for_candidate(cand_obj.id))

    return new_candidates


async def _collect_hh(token: str, vacancy_id: str) -> list[dict]:
    from app.services import hh_api
    items = []
    page = 0
    while True:
        result = await hh_api.get_negotiations(token, vacancy_id, page=page)
        items.extend(result["items"])
        if page + 1 >= result.get("pages", 1):
            break
        page += 1
    return items


async def _run() -> None:
    while True:
        try:
            await _sync_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[Sync] Unexpected error: {e}")

        interval = _DEFAULT_INTERVAL
        try:
            from app.db.session import SessionLocal
            from app.models.recruitment import RecruitmentSource
            db = SessionLocal()
            try:
                rows = db.query(RecruitmentSource.sync_interval_minutes).filter(
                    RecruitmentSource.is_active == True
                ).all()
                if rows:
                    interval = min(r[0] for r in rows) * 60
            finally:
                db.close()
        except Exception:
            pass

        await asyncio.sleep(interval)


def start() -> None:
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_run())
    logger.info("[Sync] Recruitment sync task started")


def stop() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()


async def run_now() -> None:
    """Manual trigger: runs one sync cycle immediately."""
    await _sync_once()
