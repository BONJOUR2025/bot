"""Public endpoint that receives Avito messenger webhooks.

Deliberately outside the authenticated router tree: Avito cannot present a
session token, so the URL's own secret path segment is what authenticates the
caller (Avito offers no request signature). The secret is generated once and
kept in config.json, so rotating it never requires a code change.

Two safeguards on top of the secret, because this endpoint can cause the bot
to message real candidates:

* IP logging, NOT filtering. Avito publishes egress ranges, but those are
  documented for the *applications* webhook: the very first real messenger
  webhook after go-live arrived from 176.114.125.109, outside every published
  range, and was rejected — with polling quietly masking the breakage. Since
  the published list demonstrably doesn't describe this hook's traffic,
  blocking on it produces silent false negatives, which is worse here than
  the marginal hardening it buys on top of a 43-char unguessable secret.
  Unexpected origins are therefore logged (so a real change of behaviour is
  still visible) but never rejected.
* Fast 200 + background processing — screening does LLM calls and platform
  sends that take seconds; holding the webhook connection open for that risks
  Avito timing out and retrying (or disabling the hook), so the work is
  handed off and the response returns immediately.
"""
from __future__ import annotations

import hmac
import ipaddress
import logging
import secrets
from types import SimpleNamespace

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

log = logging.getLogger(__name__)

router = APIRouter(prefix="/avito", tags=["Avito webhook"])

_SECRET_KEY = "avito_webhook_secret"

# Documented in Avito's own webhook docs (see /job/v1/applications/webhook).
_AVITO_NETWORKS = [
    ipaddress.ip_network("185.89.12.0/22"),
    ipaddress.ip_network("146.158.48.0/21"),
    ipaddress.ip_network("185.79.237.224/28"),
    ipaddress.ip_network("87.245.204.32/28"),
]


def get_or_create_secret() -> str:
    """Secret path segment for our webhook URL, created on first use."""
    from app.services.config_service import ConfigService

    svc = ConfigService()
    current = (svc.load().get(_SECRET_KEY) or "").strip()
    if current:
        return current
    generated = secrets.token_urlsafe(32)
    svc.patch({_SECRET_KEY: generated})
    return generated


def webhook_path(secret: str | None = None) -> str:
    return f"/api/avito/webhook/{secret or get_or_create_secret()}"


def _client_ip(request: Request) -> str | None:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else None


def _ip_is_avito(raw_ip: str | None) -> bool | None:
    """True/False when the IP can be judged, None when there is nothing
    meaningful to check (loopback/private — i.e. the tunnel hid the origin)."""
    if not raw_ip:
        return None
    try:
        ip = ipaddress.ip_address(raw_ip)
    except ValueError:
        return None
    if ip.is_loopback or ip.is_private:
        return None
    return any(ip in net for net in _AVITO_NETWORKS)


def _extract_message(body: dict) -> dict | None:
    """Normalise Avito's webhook body to {chat_id, message_id, text, author_id}.

    Tolerant by design: the exact envelope has changed between webhook
    versions (v1/v2/v3 all wrap the message differently), and a shape we don't
    recognise must degrade to "ignored, polling will catch it" rather than
    raise — the poller remains the safety net either way.
    """
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    value = payload.get("value") if isinstance(payload.get("value"), dict) else {}
    if not value and isinstance(body.get("value"), dict):
        value = body["value"]
    if not value:
        value = body

    chat_id = str(value.get("chat_id") or value.get("chatId") or "").strip()
    message_id = str(value.get("id") or value.get("message_id") or "").strip()
    if not chat_id or not message_id:
        return None

    content = value.get("content") if isinstance(value.get("content"), dict) else {}
    text = (content.get("text") or value.get("text") or "").strip()

    return {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "author_id": str(value.get("author_id") or value.get("user_id") or "").strip(),
        "type": str(value.get("type") or "").strip(),
    }


async def _process(msg: dict) -> None:
    """Route one incoming candidate message into the quick screen."""
    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate, RecruitmentSource
    from app.services import avito_api, quick_screening
    from app.services.recruitment_sync import _route_to_quick_screening

    # Разговор без опроса: заполняется ниже, а уведомление уходит уже после
    # закрытия сессии — держать её открытой на время сетевого вызова в
    # Telegram незачем, а делать это внутри try/except значило бы списать
    # ошибку отправки на «не смогли найти кандидата».
    notify_args: tuple | None = None
    cand_id = token = src_snapshot = None

    db = SessionLocal()
    try:
        src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "avito").first()
        if not src or not (src.client_id and src.client_secret):
            return
        # Our own outgoing messages come back through the same hook.
        if msg["author_id"] and str(src.employer_id) == msg["author_id"]:
            return

        candidate = db.query(Candidate).filter(
            Candidate.source == "avito",
            Candidate.platform_chat_id == msg["chat_id"],
        ).first()
        if not candidate:
            log.info("avito webhook: no candidate for chat %s, ignoring", msg["chat_id"])
            return  # not a candidate we track (or not imported yet)
        # Витрина для карточки пишется до всех проверок ниже: последнее
        # сообщение полезно видеть и у кандидата, чей опрос уже завершён или
        # передан админу — именно там переписку ведут руками.
        if msg["text"]:
            quick_screening.record_last_message(db, candidate, msg["text"], "applicant")

        state_status = quick_screening.load_state(candidate).get("status")
        if state_status != "asking":
            # Опрос не идёт — но разговор идёт. Раньше здесь был просто выход,
            # и сообщение оседало в карточке, о которой никто не знал: человек
            # отвечал на наше же «когда вам удобно поговорить?» и не получал
            # ничего. Отвечать за админа мы не вправе, а сказать ему — обязаны.
            log.info("avito webhook: candidate %s is not in an active screen (%s), notifying admin",
                     candidate.id, state_status)
            notify_args = (candidate.id, candidate.name, msg["text"], msg["message_id"])
        elif msg["text"]:
            token = (await avito_api.get_token(src.client_id, src.client_secret))["access_token"]
            cand_id = candidate.id
            # Снимок вместо самого ORM-объекта: ниже сессия уже закрыта, а
            # отправка сообщения читает src.employer_id — на detached-инстансе это
            # отказ в самый неудобный момент (кандидат ждёт ответа).
            src_snapshot = SimpleNamespace(source="avito", employer_id=src.employer_id)
        # else: картинка или системное сообщение — ответа в нём нет
    except Exception:
        log.warning("avito webhook: failed to resolve candidate", exc_info=True)
        return
    finally:
        db.close()

    if notify_args:
        from app.services.recruitment_sync import notify_unhandled_message
        try:
            await notify_unhandled_message(*notify_args, "avito")
        except Exception:
            log.warning("avito webhook: admin notification failed for candidate %s",
                        notify_args[0], exc_info=True)
        return

    if token is None:
        return

    try:
        await _route_to_quick_screening(cand_id, src_snapshot, token, msg["text"], msg["message_id"])
        log.info("avito webhook: routed message %s for candidate %s", msg["message_id"], cand_id)
    except Exception:
        log.warning("avito webhook: routing failed for candidate %s", cand_id, exc_info=True)


@router.post("/webhook/{secret}")
async def avito_webhook(secret: str, request: Request, background: BackgroundTasks):
    if not hmac.compare_digest(secret, get_or_create_secret()):
        raise HTTPException(404, "Not found")  # 404, not 403 — don't confirm the path exists

    # Observability only — see the module docstring for why this must not
    # reject: the secret is the gate, and Avito's real messenger egress IPs
    # are not the ones it publishes for the applications webhook.
    if _ip_is_avito(_client_ip(request)) is False:
        log.info("avito webhook: request from IP outside published Avito ranges (%s)",
                 _client_ip(request))

    try:
        body = await request.json()
    except Exception:
        # Logged, not silent: an "ignored" with no trace is indistinguishable
        # from "never arrived" when diagnosing, which is exactly the question
        # asked whenever this feature looks dead.
        log.info("avito webhook: body is not valid JSON, ignoring")
        return {"status": "ignored"}  # never 4xx/5xx a webhook over a bad body
    if not isinstance(body, dict):
        log.info("avito webhook: body is not an object, ignoring")
        return {"status": "ignored"}

    msg = _extract_message(body)
    if not msg:
        log.info("avito webhook: unrecognised payload shape, ignoring: %s", str(body)[:500])
        return {"status": "ignored"}
    if msg["type"] and msg["type"] != "text":
        log.info("avito webhook: non-text message (%s), ignoring", msg["type"])
        return {"status": "ignored"}

    # The one line that proves Avito reaches us at all — without it, a webhook
    # silently dropped by the IP allowlist looks identical to one that was
    # never sent, and polling would quietly mask the difference.
    log.info("avito webhook: accepted message %s in chat %s", msg["message_id"], msg["chat_id"])
    background.add_task(_process, msg)
    return {"status": "ok"}
