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

            for link in links:
                try:
                    new_count = await _sync_link(db, src, link, token)
                    link.last_synced_at = datetime.utcnow()
                    link.last_sync_count = new_count
                    src.last_error = ""
                    db.commit()
                    if new_count:
                        logger.info(f"[Sync] {src.source} vacancy={link.external_vacancy_id}: +{new_count} candidates")
                        await _notify_new_candidates(src.source, link, new_count)
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
    finally:
        db.close()


async def _notify_new_candidates(source: str, link, count: int) -> None:
    from app.services.notify import send_notification
    src_label = "hh.ru" if source == "hh" else "Авито"
    vac_id = link.external_vacancy_id
    await send_notification(
        f"👤 <b>Новые отклики ({src_label})</b>\n"
        f"Вакансия #{vac_id}: +{count} {'кандидат' if count == 1 else 'кандидата' if count < 5 else 'кандидатов'}"
    )


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
                latest = messages[-1]
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
                    # New message from applicant — notify
                    c.last_msg_id = latest_id
                    own_db.commit()
                finally:
                    own_db.close()

                logger.info("[Sync] hh new applicant message from %s, sending notification", name)
                await send_notification(
                    f"💬 <b>Новое сообщение от кандидата (hh.ru)</b>\n"
                    f"<b>{name}</b>: {latest['text'][:200]}"
                )
            except Exception as exc:
                logger.warning("[Sync] hh message check failed for neg=%s (%s): %s", neg_id, name, exc)

    await asyncio.gather(*[
        check_one(c.id, c.external_id, c.name, c.last_msg_id)
        for c in candidates
    ])


async def _sync_link(db, src, link, token: str) -> int:
    from app.models.recruitment import Candidate
    from app.services import hh_api, avito_api

    if src.source == "hh":
        new_items = await _collect_hh(token, link.external_vacancy_id)
    elif src.source == "avito":
        new_items = await avito_api.get_applications_for_vacancy(token, src.employer_id, link.external_vacancy_id)
    else:
        return 0

    count = 0
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
            count += 1
    db.flush()
    return count


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
