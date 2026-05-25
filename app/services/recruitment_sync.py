"""Background sync: pulls new candidates from hh.ru and Avito into the CRM."""
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None
_DEFAULT_INTERVAL = 15 * 60  # fallback 15 min; actual per-source interval used inside loop


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
            # For Avito, refresh token if needed (client_credentials are short-lived)
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
                except Exception as e:
                    logger.warning(f"[Sync] {src.source} link {link.id} error: {e}")
                    src.last_error = str(e)
                    db.commit()
    finally:
        db.close()


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

        # Sleep for the shortest active interval among sources, default 15 min
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
