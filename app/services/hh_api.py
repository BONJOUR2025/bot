"""hh.ru Employer API client."""
from urllib.parse import urlencode

import httpx

from app.utils.logger import get_service_logger

log = get_service_logger("hh")

HH_BASE = "https://api.hh.ru"
HH_AUTH_BASE = "https://hh.ru"
TIMEOUT = 15.0


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": "HRBot/1.0 (admin-panel)",
        "HH-User-Agent": "HRBot/1.0 (admin-panel)",
    }


async def verify_token(access_token: str) -> dict:
    """
    Returns {"employer_id": str, "employer_name": str}
    or raises ValueError with a human-readable message.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # 1. Get current user info to find employer_id
        r = await client.get(f"{HH_BASE}/me", headers=_headers(access_token))
        if r.status_code == 403:
            raise ValueError("Токен не имеет прав работодателя. Убедитесь, что авторизованы как работодатель.")
        if r.status_code == 401:
            raise ValueError("Токен недействителен или истёк. Получите новый на hh.ru.")
        r.raise_for_status()
        me = r.json()

        employer = me.get("employer")
        if not employer:
            raise ValueError("Аккаунт не является работодателем на hh.ru.")

        return {
            "employer_id": str(employer["id"]),
            "employer_name": employer.get("name", ""),
        }


async def get_vacancies(access_token: str, employer_id: str) -> list[dict]:
    """Returns list of active vacancies for the employer."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        params = {
            "employer_id": employer_id,
            "per_page": 100,
            "page": 0,
            "status": "open",
        }
        r = await client.get(f"{HH_BASE}/vacancies", headers=_headers(access_token), params=params)
        r.raise_for_status()
        data = r.json()
        return [
            {
                "id": str(v["id"]),
                "title": v["name"],
                "area": v.get("area", {}).get("name", ""),
                "url": v.get("alternate_url", ""),
            }
            for v in data.get("items", [])
        ]


def build_auth_url(client_id: str, redirect_uri: str) -> str:
    """Return the hh.ru OAuth2 authorization URL."""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }
    return f"{HH_AUTH_BASE}/oauth/authorize?{urlencode(params)}"


async def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            f"{HH_BASE}/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        if r.status_code != 200:
            raise ValueError(f"Не удалось получить токен от hh.ru: {r.text}")
        return r.json()


async def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    """Refresh an expired access token using the stored refresh token."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            f"{HH_BASE}/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        if r.status_code != 200:
            raise ValueError(f"Не удалось обновить токен hh.ru: {r.text}")
        return r.json()


async def get_negotiations(access_token: str, vacancy_id: str, page: int = 0) -> dict:
    """
    Fetch active negotiations (responses) for a vacancy.
    Returns {"found": int, "items": [...]} where each item has candidate info.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        params = {
            "vacancy_id": vacancy_id,
            "per_page": 50,
            "page": page,
        }
        r = await client.get(
            f"{HH_BASE}/negotiations/response",
            headers=_headers(access_token),
            params=params,
        )
        if r.status_code == 404:
            return {"found": 0, "items": []}
        r.raise_for_status()
        data = r.json()

        # Collect basic data first, then enrich with full resumes where accessible
        raw_items = []
        for neg in data.get("items", []):
            resume = neg.get("resume") or {}

            # ── Age (available in list response) ───────────────────
            age = None
            raw_age = resume.get("age")
            if raw_age is not None:
                try:
                    age = int(raw_age)
                except Exception:
                    pass
            if age is None:
                birthday = resume.get("birthday")
                if isinstance(birthday, dict):
                    try:
                        from datetime import date as _date
                        by = birthday.get("year")
                        bm = birthday.get("month", 1)
                        bd = birthday.get("day", 1)
                        if by:
                            bday = _date(int(by), int(bm), int(bd))
                            today = _date.today()
                            age = today.year - bday.year - ((today.month, today.day) < (bday.month, bday.day))
                    except Exception:
                        pass
                elif isinstance(birthday, str) and birthday:
                    try:
                        from datetime import date as _date
                        bday = _date.fromisoformat(birthday[:10])
                        today = _date.today()
                        age = today.year - bday.year - ((today.month, today.day) < (bday.month, bday.day))
                    except Exception:
                        pass

            first = resume.get("first_name") or ""
            last = resume.get("last_name") or ""
            name = (f"{last} {first}".strip()) or neg.get("applicant_name") or "Без имени"
            resume_url = resume.get("alternate_url") or ""
            resume_id = resume.get("id") or ""
            can_view = bool(resume.get("can_view_full_info"))

            # Photo available in list response
            photo_obj = resume.get("photo") or {}
            photo_url = photo_obj.get("medium") or photo_obj.get("small") or ""

            raw_items.append({
                "neg_id": str(neg["id"]),
                # Вебхук CHAT_MESSAGE_CREATED приходит с chat_id, а не с id
                # отклика — без этой связки уведомление невозможно сопоставить
                # с кандидатом. Здесь единственное место, где hh отдаёт обе
                # величины рядом.
                "chat_id": str(neg.get("chat_id") or ""),
                "name": name,
                "resume_url": resume_url,
                "resume_id": resume_id,
                "can_view": can_view,
                "age": age,
                "phone": "",
                "email": "",
                "photo_url": photo_url,
                "applied_at": neg.get("created_at") or "",
            })

        # ── Enrich: fetch full resume for contacts ─────────────────
        # hh.ru doesn't return contact in the negotiations list;
        # need a separate GET /resumes/{id} when can_view_full_info=True
        import asyncio
        sem = asyncio.Semaphore(3)  # max 3 concurrent resume fetches

        async def fetch_contacts(item: dict) -> None:
            if not item["can_view"] or not item["resume_id"]:
                return
            async with sem:
                try:
                    r2 = await client.get(
                        f"{HH_BASE}/resumes/{item['resume_id']}",
                        headers=_headers(access_token),
                    )
                    if r2.status_code != 200:
                        log.debug("hh resume %s → %s", item["resume_id"], r2.status_code)
                        return
                    full = r2.json()
                    # hh.ru returns contact as a list:
                    # [{"type": {"id": "cell"}, "value": {"formatted": "+7..."}, ...}, ...]
                    contacts_list = full.get("contact") or []
                    if isinstance(contacts_list, dict):
                        # Fallback in case structure ever changes
                        contacts_list = [contacts_list]
                    for c in contacts_list:
                        ctype = (c.get("type") or {}).get("id", "")
                        val = c.get("value") or {}
                        if ctype in ("cell", "home", "work") and not item["phone"]:
                            if isinstance(val, dict):
                                item["phone"] = (
                                    val.get("formatted")
                                    or f"+{val.get('country','')}{val.get('city','')}{val.get('number','')}".strip()
                                )
                            elif isinstance(val, str):
                                item["phone"] = val
                        elif ctype == "email" and not item["email"]:
                            item["email"] = val if isinstance(val, str) else ""
                    # birthday may be present in full resume
                    if item["age"] is None:
                        bd = full.get("birthday")
                        if isinstance(bd, dict):
                            try:
                                from datetime import date as _date
                                by = bd.get("year")
                                if by:
                                    bday = _date(int(by), int(bd.get("month", 1)), int(bd.get("day", 1)))
                                    today = _date.today()
                                    item["age"] = today.year - bday.year - ((today.month, today.day) < (bday.month, bday.day))
                            except Exception:
                                pass
                        elif isinstance(bd, str) and bd:
                            try:
                                from datetime import date as _date
                                bday = _date.fromisoformat(bd[:10])
                                today = _date.today()
                                item["age"] = today.year - bday.year - ((today.month, today.day) < (bday.month, bday.day))
                            except Exception:
                                pass
                except Exception as exc:
                    log.warning("hh resume fetch failed %s: %s", item["resume_id"], exc)

        await asyncio.gather(*[fetch_contacts(it) for it in raw_items])

        items = [
            {
                "external_id": it["neg_id"],
                # Кладём в то же поле, что и Авито: для hh отвечать по-прежнему
                # надо в negotiation (external_id), но вебхук о новом сообщении
                # приходит с chat_id — по нему и ищем кандидата.
                "platform_chat_id": it["chat_id"],
                "name": it["name"],
                "phone": it["phone"],
                "email": it["email"],
                "resume_url": it["resume_url"],
                "photo_url": it["photo_url"],
                "age": it["age"],
                "applied_at": it["applied_at"],
                "notes": f"Отклик hh.ru: {it['resume_url']}" if it["resume_url"] else "Отклик hh.ru",
            }
            for it in raw_items
        ]

        return {
            "found": data.get("found", 0),
            "pages": data.get("pages", 1),
            "items": items,
        }


# ── Messaging ─────────────────────────────────────────────────────

async def get_messages(access_token: str, neg_id: str) -> list[dict]:
    """Return messages for a negotiation, oldest first."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(
            f"{HH_BASE}/negotiations/{neg_id}/messages",
            headers=_headers(access_token),
        )
        if r.status_code in (403, 404):
            return []
        r.raise_for_status()
        items = r.json().get("items", [])
        return [
            {
                "id": str(m.get("id") or ""),
                "text": m.get("text") or "",
                "created_at": m.get("created_at") or "",
                "author_type": (m.get("author") or {}).get("participant_type", ""),
                "author_name": (m.get("author") or {}).get("name", ""),
                "read": m.get("read", True),
            }
            for m in reversed(items)  # hh returns newest first
        ]


_HH_ERROR_HINTS = {
    "disabled_by_employer": (
        "hh.ru запретил переписку по этому отклику — обычно это значит, что вакансия "
        "на hh.ru архивирована/закрыта, либо у вашего тарифа нет доступа к сообщениям "
        "по этому отклику. Сообщение не отправлено, проверьте вакансию на hh.ru."
    ),
}


async def send_message(access_token: str, neg_id: str, text: str) -> dict:
    """Send a message to a candidate in a negotiation."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            f"{HH_BASE}/negotiations/{neg_id}/messages",
            headers=_headers(access_token),
            data={"message": text},
        )
        if r.status_code not in (200, 201):
            hint = None
            try:
                errors = (r.json() or {}).get("errors") or []
                for err in errors:
                    hint = _HH_ERROR_HINTS.get(err.get("value"))
                    if hint:
                        break
            except Exception:
                pass
            if hint:
                raise ValueError(f"hh.ru: не удалось отправить сообщение — {hint}")
            raise ValueError(f"hh.ru: не удалось отправить сообщение ({r.status_code}): {r.text[:200]}")
        return r.json() if r.content else {}


# ── Stage synchronisation ──────────────────────────────────────────

# Map internal stage keys → hh.ru employer action IDs
_STAGE_TO_HH_ACTION: dict[str, str] = {
    "отказ":         "discard_by_employer",
    "собеседование": "phone_interview",
    "ждем":          "hold",
}


async def sync_negotiation_stage(access_token: str, neg_id: str, new_stage: str,
                                  rejection_message: str | None = None,
                                  hh_message: str | None = None) -> bool:
    """
    Push a stage change to hh.ru using the action URL from the negotiation's own actions list.
    Returns True if the action was applied, False if not applicable / unavailable.
    Never raises — logs warnings on failure.
    """
    action_id = _STAGE_TO_HH_ACTION.get(new_stage)
    if not action_id:
        return False

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Fetch the negotiation to get the list of currently available actions
        r_neg = await client.get(
            f"{HH_BASE}/negotiations/{neg_id}",
            headers=_headers(access_token),
        )
        if r_neg.status_code != 200:
            log.warning("hh GET negotiation %s → HTTP %s", neg_id, r_neg.status_code)
            return False

        neg_data = r_neg.json()
        actions = neg_data.get("actions") or []
        action = next((a for a in actions if a.get("id") == action_id), None)

        if action is None:
            available = [a.get("id") for a in actions]
            log.info(
                "hh action '%s' not available for neg %s (available: %s)",
                action_id, neg_id, available,
            )
            return False

        if not action.get("enabled", True):
            log.info("hh action '%s' is disabled for neg %s", action_id, neg_id)
            return False

        log.info("hh action object for '%s' neg %s: %s", action_id, neg_id, action)

        url = action.get("url") or f"{HH_BASE}/negotiations/{action_id}/{neg_id}"
        method = (action.get("method") or "PUT").upper()

        # Build form data from action arguments if any are required
        arguments = action.get("arguments") or []
        form_data: dict = {}
        for arg in arguments:
            if arg.get("required") and arg.get("value") is not None:
                form_data[arg["id"]] = arg["value"]
        log.info("hh action '%s' arguments: %s → form_data: %s", action_id, arguments, form_data)

        r = await client.request(method, url, headers=_headers(access_token),
                                 data=form_data if form_data else None)
        if r.status_code not in (200, 201, 204):
            log.warning(
                "hh action '%s' neg %s → HTTP %s: %s",
                action_id, neg_id, r.status_code, r.text[:200],
            )
            return False

        log.info("hh action '%s' applied for neg %s", action_id, neg_id)

        # Send message to candidate if provided
        msg_text = rejection_message if new_stage == "отказ" else hh_message
        if msg_text and msg_text.strip():
            try:
                r_msg = await client.post(
                    f"{HH_BASE}/negotiations/{neg_id}/messages",
                    headers=_headers(access_token),
                    data={"message": msg_text.strip()},
                )
                if r_msg.status_code in (200, 201):
                    log.info("hh message sent for neg %s (stage=%s)", neg_id, new_stage)
                else:
                    log.warning("hh message failed for neg %s: HTTP %s %s",
                                neg_id, r_msg.status_code, r_msg.text[:200])
            except Exception as exc:
                log.warning("hh message error for neg %s: %s", neg_id, exc)

        return True


# ── Webhooks ──────────────────────────────────────────────────────
# hh doesn't document these in its GitHub docs repo — they live only in the
# OpenAPI spec (api.hh.ru/openapi/specification/public, tag Webhook-API).
#
# Differences from Avito's webhooks that shape the code around this:
# * one URL per application — a single endpoint has to serve every event;
# * hh retries with growing backoff unless we answer 2xx within 5 seconds,
#   and expects 409 (not 200) for a duplicate it already delivered;
# * a subscription that keeps failing gets queued for blocking, with a mail
#   to the app developer — so silently 500-ing here has a real cost;
# * delivery is explicitly not guaranteed, so polling stays as the net.

WEBHOOK_EVENT_NEW_MESSAGE = "CHAT_MESSAGE_CREATED"
WEBHOOK_EVENT_NEW_RESPONSE = "NEW_RESPONSE_OR_INVITATION_VACANCY"


async def list_webhook_subscriptions(access_token: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(f"{HH_BASE}/webhook/subscriptions", headers=_headers(access_token))
        if r.status_code == 404:
            return []
        r.raise_for_status()
        data = r.json() or {}
    return data.get("items") or data.get("subscriptions") or []


async def subscribe_webhook(access_token: str, url: str, actions: list[str]) -> dict:
    """Subscribe the given URL to hh events."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            f"{HH_BASE}/webhook/subscriptions",
            headers={**_headers(access_token), "Content-Type": "application/json"},
            json={"url": url, "actions": [{"type": a} for a in actions]},
        )
        if r.status_code in (200, 201, 204):
            return r.json() if r.content else {}
        raise ValueError(
            f"hh.ru не принял подписку на вебхук ({r.status_code}): {r.text[:300]}. "
            "Проверьте, что URL доступен снаружи и у приложения есть права работодателя."
        )


async def delete_webhook_subscription(access_token: str, subscription_id: str) -> None:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.delete(
            f"{HH_BASE}/webhook/subscriptions/{subscription_id}",
            headers=_headers(access_token),
        )
        if r.status_code not in (200, 204, 404):
            raise ValueError(f"hh.ru не снял подписку ({r.status_code}): {r.text[:300]}")
