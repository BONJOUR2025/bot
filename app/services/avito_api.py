"""Avito Jobs API client."""
from datetime import datetime, timedelta

import httpx

from app.utils.logger import get_service_logger

log = get_service_logger("avito")

AVITO_BASE = "https://api.avito.ru"
TIMEOUT = 15.0


async def get_token(client_id: str, client_secret: str) -> dict:
    """
    OAuth2 client_credentials flow.
    Returns {"access_token": str, "expires_in": int} or raises ValueError.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            f"{AVITO_BASE}/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            detail = data.get("error_description") or data.get("error") or "Ошибка авторизации"
            raise ValueError(f"Авито: {detail}")
        return data


async def get_user_info(access_token: str) -> dict:
    """Returns {"employer_id": str, "employer_name": str}"""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(
            f"{AVITO_BASE}/core/v1/accounts/self",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        data = r.json()
        return {
            "employer_id": str(data["id"]),
            "employer_name": data.get("name") or data.get("email") or str(data["id"]),
        }


async def get_vacancy_by_id(access_token: str, vacancy_id: str) -> dict | None:
    """
    Fetch a single vacancy by its Avito ID.
    Returns {"id", "title", "area", "url"} or None if not found.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(
            f"{AVITO_BASE}/job/v2/vacancies/{vacancy_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if r.status_code in (402, 403, 404):
            return None
        r.raise_for_status()
        v = r.json()
        addr = v.get("addressDetails") or {}
        area = (addr.get("city") or addr.get("province") or addr.get("address") or "") if isinstance(addr, dict) else ""
        return {
            "id": str(vacancy_id),
            "title": v.get("title") or "",
            "area": area,
            "url": v.get("url") or f"https://www.avito.ru/vakansii/{vacancy_id}",
        }


async def get_applications_for_vacancy(
    access_token: str,
    user_id: str,
    avito_vacancy_id: str,
    days_back: int = 30,
) -> list[dict]:
    """
    Fetch job applications for a vacancy using the Avito Jobs API v1 two-step flow:
    1. GET /job/v1/applications/get_ids — returns application IDs
    2. POST /job/v1/applications/get_by_ids — returns full applicant data
    """
    since = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        headers = {"Authorization": f"Bearer {access_token}"}

        # Step 1: get IDs
        r = await client.get(
            f"{AVITO_BASE}/job/v1/applications/get_ids",
            headers=headers,
            params={
                "vacancyIds": avito_vacancy_id,
                "createdAtFrom": since,
            },
        )
        if r.status_code == 402:
            # Avito's own wording: "Перейдите на Максимальную подписку в
            # Авито.Работе, чтобы получить доступ к API". Raised rather than
            # returning [] so the source shows a real reason instead of
            # looking like a vacancy with no responses.
            raise ValueError(
                "Авито: доступ к API откликов требует Максимальной подписки в Авито.Работе "
                f"(аккаунт {user_id}). Мессенджер при этом может быть доступен."
            )
        if r.status_code in (404, 403):
            return []
        r.raise_for_status()
        applies_meta = r.json().get("applies") or []
        ids = [a["id"] for a in applies_meta if a.get("id")]
        log.info("Avito get_ids vacancy=%s since=%s → %d ids", avito_vacancy_id, since, len(ids))
        if not ids:
            return []

        # Step 2: get full details (max 100 per request)
        r2 = await client.post(
            f"{AVITO_BASE}/job/v1/applications/get_by_ids",
            headers=headers,
            json={"ids": ids[:100]},
        )
        if r2.status_code in (404, 403):
            return []
        r2.raise_for_status()
        applies = r2.json().get("applies") or []
        log.info("Avito get_by_ids → %d applications", len(applies))

    result = []
    for app in applies:
        app_id = str(app.get("id") or "")
        applicant = app.get("applicant") or {}
        data = applicant.get("data") or {}

        full_name = data.get("full_name") or {}
        if isinstance(full_name, dict):
            parts = [full_name.get("last_name"), full_name.get("first_name"), full_name.get("patronymic")]
            name = " ".join(p for p in parts if p) or data.get("name") or "Кандидат"
        else:
            name = data.get("name") or "Кандидат"

        contacts = app.get("contacts") or {}
        phones = contacts.get("phones") or []
        phone = phones[0].get("value", "") if phones else ""

        # Chat id for replying through the Messenger API. Empty when the
        # applicant only revealed the phone number (apply type "by_call") —
        # per Avito's docs there is simply no chat in that case, so anything
        # built on top must treat "" as "cannot write to this candidate".
        chat = contacts.get("chat") or {}
        chat_id = str(chat.get("value") or "") if isinstance(chat, dict) else ""

        age = None
        raw_age = data.get("age")
        if raw_age is not None:
            try:
                age = int(raw_age)
            except Exception:
                pass
        if age is None:
            birthday_str = data.get("birthday")
            if birthday_str:
                try:
                    from datetime import date as _date
                    bday = _date.fromisoformat(str(birthday_str)[:10])
                    today = _date.today()
                    age = today.year - bday.year - ((today.month, today.day) < (bday.month, bday.day))
                except Exception:
                    pass

        result.append({
            "external_id": app_id,
            "name": name,
            "phone": str(phone) if phone else "",
            "email": "",
            "resume_url": "",
            "age": age,
            "notes": "Авито отклик",
            "platform_chat_id": chat_id,
        })

    return result


# ── Messenger ────────────────────────────────────────────────────────────────
# Used to talk to a job applicant in Avito's own chat (see quick_screening).
# The chat id comes from an application's contacts.chat.value.
#
# Note: for Работа, Avito gates the Messenger API behind the "Максимальный"
# subscription tier — a 403 here usually means the tariff, not a bad token.

MESSAGE_MAX_LEN = 1000  # hard limit from Avito's sendMessage schema


async def send_message(access_token: str, user_id: str, chat_id: str, text: str) -> dict:
    """Send a text message into an Avito chat."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            f"{AVITO_BASE}/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"type": "text", "message": {"text": text[:MESSAGE_MAX_LEN]}},
        )
        if r.status_code == 403:
            raise ValueError(
                "Авито отклонил отправку сообщения (403). Messenger API в Авито Работе "
                "доступен только на тарифе «Максимальный» — проверьте тариф и права ключа "
                "(нужен scope messenger:write)."
            )
        r.raise_for_status()
        return r.json() if r.content else {}


async def get_job_chats(access_token: str, user_id: str, item_id: str,
                         max_pages: int = 10, page_size: int = 100) -> list[dict]:
    """Job applicants for a vacancy, derived from Messenger chats instead of
    the applications API.

    Avito paywalls the whole job/* section behind the "Максимальная" Работа
    subscription (402 on every endpoint, even ones needing no scope), while
    the Messenger API stays available. Each chat carries the listing it
    belongs to (context.value.id), so filtering chats by the vacancy's item id
    yields exactly its applicants.

    Returned in the same shape as get_applications_for_vacancy() so the sync
    can use either source interchangeably. Necessarily thinner: phone, age,
    citizenship and résumé links live only in the paid API. Applicants who
    only revealed a phone ("by_call") have no chat and therefore never appear
    here — which is consistent, since there would be no way to write to them.
    """
    result = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        headers = {"Authorization": f"Bearer {access_token}"}
        for page in range(max_pages):
            r = await client.get(
                f"{AVITO_BASE}/messenger/v2/accounts/{user_id}/chats",
                headers=headers,
                params={"limit": page_size, "offset": page * page_size},
            )
            if r.status_code == 403:
                raise ValueError(
                    "Авито отклонил чтение чатов (403). Нужен ключ основного аккаунта компании "
                    "со scope messenger:read."
                )
            r.raise_for_status()
            chats = (r.json() or {}).get("chats") or []
            if not chats:
                break

            for chat in chats:
                context = chat.get("context") or {}
                value = context.get("value") or {}
                if str(value.get("id") or "") != str(item_id):
                    continue

                # The counterparty is whichever participant isn't us.
                name = "Кандидат"
                for u in chat.get("users") or []:
                    if str(u.get("id") or "") != str(user_id):
                        name = u.get("name") or name
                        break

                created_ts = chat.get("created")
                applied_at = None
                if created_ts:
                    try:
                        applied_at = datetime.utcfromtimestamp(int(created_ts)).isoformat()
                    except Exception:
                        applied_at = None

                chat_id = str(chat.get("id") or "")
                result.append({
                    # No application id is available on this path, so the chat
                    # id doubles as the stable external key.
                    "external_id": chat_id,
                    "name": name,
                    "phone": "",
                    "email": "",
                    "resume_url": "",
                    "age": None,
                    "notes": "Авито отклик (через мессенджер)",
                    "platform_chat_id": chat_id,
                    "applied_at": applied_at,
                })

            if len(chats) < page_size:
                break

    log.info("Avito job chats item=%s → %d applicants", item_id, len(result))
    return result


async def get_messages(access_token: str, user_id: str, chat_id: str, limit: int = 50) -> list[dict]:
    """Return chat messages, normalised to the same shape hh_api.get_messages uses
    so callers don't branch per platform:
        {"id", "text", "author_type": "applicant"|"employer", "created_at"}

    Avito marks direction from *our* side: "in" is a message from the applicant.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(
            f"{AVITO_BASE}/messenger/v3/accounts/{user_id}/chats/{chat_id}/messages/",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"limit": limit},
        )
        if r.status_code == 403:
            raise ValueError(
                "Авито отклонил чтение чата (403). Messenger API в Авито Работе доступен "
                "только на тарифе «Максимальный» (нужен scope messenger:read)."
            )
        r.raise_for_status()
        data = r.json()

    # The endpoint returns a bare array; tolerate a wrapped form too, since a
    # shape change here would otherwise surface as a confusing AttributeError.
    items = data if isinstance(data, list) else (data.get("messages") or [])

    result = []
    for m in items:
        if m.get("type") != "text":
            continue  # images/calls/system carry no answer we can screen on
        content = m.get("content") or {}
        text = (content.get("text") or "").strip()
        if not text:
            continue
        result.append({
            "id": str(m.get("id") or ""),
            "text": text,
            "author_type": "applicant" if m.get("direction") == "in" else "employer",
            "created_at": m.get("created") or 0,
        })
    return result


# Avito API does not provide an endpoint to list the employer's own vacancies.
# Users must enter vacancy IDs manually (taken from the vacancy URL on avito.ru).
async def get_vacancies(access_token: str, user_id: str) -> list[dict]:
    return []


async def get_chats_for_vacancy(access_token: str, user_id: str, avito_vacancy_id: str) -> list[dict]:
    return await get_applications_for_vacancy(access_token, user_id, avito_vacancy_id)
