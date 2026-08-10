"""Public endpoint that receives hh.ru webhooks (CHAT_MESSAGE_CREATED).

Same shape as the Avito one (secret in the URL path, fast ack, background
processing), but hh's contract differs in three ways that drive the code here:

* **The callback carries no message text** — only chat_id, message_id, role
  and type. So the text still has to be fetched, from the negotiations API.
  The win is the trigger: seconds instead of the polling interval.
* **chat_id ≠ negotiation id.** We reply into a negotiation (Candidate.
  external_id) but the webhook identifies the conversation by chat_id, so the
  candidate is looked up by `platform_chat_id`, which the sync now fills for
  hh as well (see hh_api.get_negotiations).
* **409 means "already have it".** hh retries with growing backoff unless it
  gets 2xx within 5 seconds, and treats 409 as a successful duplicate ack —
  answering 200 to a duplicate would be fine too, but 409 is what tells hh
  its dedup is working. A subscription that keeps not answering as expected
  gets queued for blocking, so this endpoint must stay fast and quiet.

Delivery is explicitly not guaranteed by hh, so polling remains the net.
"""
from __future__ import annotations

import hmac
import logging
import secrets

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

log = logging.getLogger(__name__)

router = APIRouter(prefix="/hh", tags=["hh webhook"])

_SECRET_KEY = "hh_webhook_secret"

EVENT_NEW_MESSAGE = "CHAT_MESSAGE_CREATED"


def get_or_create_secret() -> str:
    from app.services.config_service import ConfigService

    svc = ConfigService()
    current = (svc.load().get(_SECRET_KEY) or "").strip()
    if current:
        return current
    generated = secrets.token_urlsafe(32)
    svc.patch({_SECRET_KEY: generated})
    return generated


def webhook_path(secret: str | None = None) -> str:
    return f"/api/hh/webhook/{secret or get_or_create_secret()}"


def extract_message_event(body: dict) -> dict | None:
    """Normalise hh's envelope to what we act on, or None if it isn't a
    candidate's chat message we should react to.

    Tolerant on purpose: an unrecognised shape must degrade to "ignored,
    polling will catch it" rather than raise — same reasoning as Avito.
    """
    if not isinstance(body, dict):
        return None
    if (body.get("action_type") or "") != EVENT_NEW_MESSAGE:
        return None
    payload = body.get("payload")
    if not isinstance(payload, dict):
        return None

    chat_id = str(payload.get("chat_id") or "").strip()
    message_id = str(payload.get("message_id") or "").strip()
    if not chat_id or not message_id:
        return None
    # PARTICIPANT_JOINED/LEFT carry no answer; only SIMPLE is a real message.
    if (payload.get("message_type") or "") != "SIMPLE":
        return None
    # Our own (and bot) messages come back through the same subscription.
    if (payload.get("role") or "") != "APPLICANT":
        return None

    return {
        "chat_id": chat_id,
        "message_id": message_id,
        "event_id": str(body.get("id") or ""),
    }


async def _process(event: dict) -> None:
    """Fetch the actual message for this chat and feed it to the screen."""
    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate, RecruitmentSource
    from app.services import hh_api, quick_screening
    from app.services.recruitment_sync import _route_to_quick_screening

    db = SessionLocal()
    try:
        src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "hh").first()
        if not src or not src.access_token:
            return
        candidate = db.query(Candidate).filter(
            Candidate.source == "hh",
            Candidate.platform_chat_id == event["chat_id"],
        ).first()
        if not candidate:
            # Normal right after go-live: candidates imported before we began
            # storing chat_id have none yet, and the sync backfills it on its
            # next pass. Polling answers them meanwhile.
            log.info("hh webhook: no candidate for chat %s, ignoring", event["chat_id"])
            return
        cand_id, neg_id = candidate.id, candidate.external_id
        token = src.access_token
        src_snapshot = type("Src", (), {"source": "hh", "employer_id": src.employer_id})()
    except Exception:
        log.warning("hh webhook: failed to resolve candidate", exc_info=True)
        return
    finally:
        db.close()

    try:
        messages = await hh_api.get_messages(token, neg_id)
        applicant = [m for m in messages if m.get("author_type") == "applicant"]
        if not applicant:
            return
        latest = applicant[-1]  # get_messages returns oldest-first
        text = (latest.get("text") or "").strip()
        if not text:
            return

        own = SessionLocal()
        try:
            c = own.query(Candidate).filter(Candidate.id == cand_id).first()
            if c:
                quick_screening.record_last_message(own, c, text, "applicant")
        finally:
            own.close()

        await _route_to_quick_screening(cand_id, src_snapshot, token, text, latest.get("id", ""))
        log.info("hh webhook: routed message for candidate %s (chat %s)", cand_id, event["chat_id"])
    except Exception:
        log.warning("hh webhook: routing failed for candidate %s", cand_id, exc_info=True)


# Event ids already accepted, so a retry isn't processed twice. In-memory on
# purpose: hh retries within minutes, and a restart losing this only costs one
# redundant fetch — the screening itself dedupes by message id anyway.
_seen_events: set[str] = set()
_SEEN_MAX = 2000


@router.post("/webhook/{secret}")
async def hh_webhook(secret: str, request: Request, background: BackgroundTasks):
    if not hmac.compare_digest(secret, get_or_create_secret()):
        raise HTTPException(404, "Not found")

    try:
        body = await request.json()
    except Exception:
        log.info("hh webhook: body is not valid JSON, ignoring")
        return {"status": "ignored"}

    event = extract_message_event(body)
    if not event:
        # Not an error: we subscribe to a single URL and hh sends every event
        # type there, most of which we don't act on.
        log.debug("hh webhook: event not actionable (%s)", (body or {}).get("action_type"))
        return {"status": "ignored"}

    event_id = event["event_id"] or f"{event['chat_id']}:{event['message_id']}"
    if event_id in _seen_events:
        # hh's own contract: 409 acknowledges a duplicate as delivered.
        log.info("hh webhook: duplicate event %s", event_id)
        return Response(status_code=409)
    _seen_events.add(event_id)
    if len(_seen_events) > _SEEN_MAX:
        _seen_events.clear()

    log.info("hh webhook: accepted message %s in chat %s", event["message_id"], event["chat_id"])
    background.add_task(_process, event)
    return {"status": "ok"}
