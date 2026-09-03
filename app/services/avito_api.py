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
    days_back: int = 180,
) -> list[dict]:
    """
    Fetch job applications for a vacancy using the Avito Jobs API v1 two-step flow:
    1. GET /job/v1/applications/get_ids — returns application IDs
    2. POST /job/v1/applications/get_by_ids — returns full applicant data

    Окно было 30 дней, и это тихо обрезало историю: по боевому объявлению
    оно давало 7 откликов вместо 23. Кандидат, откликнувшийся 19 июня, в
    выдачу не попадал — а его чат был жив, он отвечал на наши вопросы, и
    в воронке он оказался только как безымянный «Олег» из мессенджера.

    Дело в том, что мессенджер отдаёт ИМЯ АККАУНТА, а отклик — настоящие
    ФИО, телефон и возраст. Пока отклик за окном, карточка остаётся с
    ником вместо имени, и найти человека по фамилии невозможно.
    Наплыва старых карточек это не вызывает: совпадение по chat_id
    дополняет уже заведённые, а опрос им не запускается (is_new_arrival).
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
            # Резюме лежит отдельным документом; здесь только ссылка на него.
            # Забирает его get_resume ниже — синхронизация делает это одним
            # запросом на кандидата, а не на каждый показ карточки.
            "resume_id": str(applicant.get("resume_id") or ""),
            "age": age,
            "notes": "Авито отклик",
            "platform_chat_id": chat_id,
        })

    return result


# ── Messenger webhooks ───────────────────────────────────────────────────────
# Push delivery of incoming candidate messages, so a reply is acted on within
# seconds instead of waiting for the next polling cycle (up to an hour).
#
# Polling is deliberately NOT removed when a webhook is active: a webhook
# Avito failed to deliver (our tunnel down — it restarts often enough that a
# watchdog exists for it) is gone for good, whereas the poll simply catches
# it on the next pass. Webhook = speed, polling = safety net.


async def subscribe_messenger_webhook(access_token: str, url: str) -> dict:
    """Subscribe to incoming-message notifications for this account.

    Avito checks the URL is reachable from their network at subscribe time and
    refuses to create the hook otherwise, so a failure here usually means the
    public URL/tunnel is down rather than a bad token.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            f"{AVITO_BASE}/messenger/v3/webhook",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"url": url},
        )
        if r.status_code == 403:
            raise ValueError(
                "Авито отклонил подписку на вебхук (403) — нужен scope messenger:read "
                "и тариф «Максимальный»."
            )
        if r.status_code not in (200, 201):
            raise ValueError(
                f"Авито не принял вебхук ({r.status_code}): {r.text[:300]}. "
                "Чаще всего это значит, что URL недоступен из сети Авито — проверьте туннель."
            )
        return r.json() if r.content else {}


async def unsubscribe_messenger_webhook(access_token: str, url: str) -> dict:
    """Remove a previously registered message webhook."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            f"{AVITO_BASE}/messenger/v1/webhook/unsubscribe",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"url": url},
        )
        if r.status_code not in (200, 201):
            raise ValueError(f"Авито не снял вебхук ({r.status_code}): {r.text[:300]}")
        return r.json() if r.content else {}


async def list_messenger_subscriptions(access_token: str) -> list[dict]:
    """Currently registered message webhooks. POST despite being a read —
    that is Avito's own contract for this endpoint, not a mistake here."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            f"{AVITO_BASE}/messenger/v1/subscriptions",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        data = r.json() or {}
    return data.get("subscriptions") or []


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
        created = m.get("created")
        created_at = ""
        if created:
            try:
                created_at = datetime.utcfromtimestamp(int(created)).isoformat()
            except Exception:
                created_at = ""
        result.append({
            "id": str(m.get("id") or ""),
            "text": text,
            "author_type": "applicant" if m.get("direction") == "in" else "employer",
            "created_at": created_at,
        })
    # Oldest first — Avito returns newest first, hh_api.get_messages already
    # normalises to chronological order, and the chat UI renders top-to-bottom
    # like any messenger. Callers that want "the latest" use max() by
    # created_at rather than relying on position, so this only affects display.
    result.reverse()
    return result


_MONTHS_IN_YEAR = 12


def _avito_experience(params: dict) -> list[dict]:
    """Места работы в том же виде, что у hh: должность, компания, даты."""
    out = []
    for e in (params.get("experience_list") or [])[:10]:
        if not isinstance(e, dict):
            continue
        out.append({
            "position": str(e.get("position") or ""),
            "company": str(e.get("company") or ""),
            "start": str(e.get("work_start") or "")[:10],
            "end": str(e.get("work_finish") or "")[:10],
            # У Авито обязанности бывают на несколько тысяч знаков — режем
            # по той же границе, что и в hh_api.build_resume_profile.
            "description": (str(e.get("responsibilities") or "")[:1500] or None),
        })
    return out


def build_resume_profile(resume: dict) -> dict:
    """Резюме Авито в тот же формат, что отдаёт hh_api.build_resume_profile.

    Формат общий намеренно: карточка кандидата, «Прозвон» и сводка ИИ уже
    умеют его читать, и площадка перестаёт быть их заботой. Поля, которых у
    Авито нет (навыки, языки), остаются пустыми — потребители и так
    рассчитаны на неполную анкету, потому что резюме на hh бывает скрыто.

    Стаж Авито отдаёт целыми годами (`experience`), hh — месяцами; здесь
    приводим к месяцам, иначе «8» прочиталось бы как восемь месяцев.
    """
    params = (resume or {}).get("params") or {}
    addr = (resume or {}).get("address_details") or {}

    years = params.get("experience")
    try:
        total_months = int(years) * _MONTHS_IN_YEAR if years is not None else None
    except (TypeError, ValueError):
        total_months = None

    salary = (resume or {}).get("salary")
    try:
        amount = int(salary) if salary else None
    except (TypeError, ValueError):
        amount = None

    schools = []
    for item in (params.get("education_list") or [])[:5]:
        if not isinstance(item, dict):
            continue
        schools.append({
            "name": str(item.get("institution") or ""),
            "organization": "",
            "result": str(item.get("specialty") or ""),
            "year": item.get("education_stop"),
        })

    return {
        "title": str((resume or {}).get("title") or ""),
        "salary": {"amount": amount, "currency": "RUR"} if amount else None,
        "total_months": total_months,
        "area": str(addr.get("location") or params.get("address") or ""),
        "metro": str(addr.get("metro") or ""),
        "citizenship": [str(params["nationality"])] if params.get("nationality") else [],
        "gender": str(params.get("pol") or ""),
        "experience": _avito_experience(params),
        "education_level": str(params.get("education") or ""),
        "education": schools,
        "skills": [],
        "languages": [],
        "employment": "",
        "schedule": str(params.get("schedule") or ""),
        "work_format": [],
        "relocation": str(params.get("moving") or ""),
        "professional_roles": [str(params["business_area"])] if params.get("business_area") else [],
        "about": str((resume or {}).get("description") or "")[:2000],
        "updated_at": str((resume or {}).get("update_time") or ""),
    }


async def get_resume(access_token: str, resume_id: str) -> dict | None:
    """Резюме кандидата по id из отклика, уже в общем формате.

    Резюме может быть удалено, скрыто или недоступно на текущем тарифе —
    во всех случаях возвращается None, а не исключение: анкета украшает
    карточку, но синхронизация откликов из-за неё падать не должна.
    """
    if not resume_id:
        return None
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            r = await client.get(
                f"{AVITO_BASE}/job/v2/resumes/{resume_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError as exc:
            log.warning("Avito resume %s: сеть недоступна (%s)", resume_id, exc)
            return None
    if r.status_code != 200:
        log.info("Avito resume %s недоступно: %s", resume_id, r.status_code)
        return None
    try:
        return build_resume_profile(r.json())
    except (ValueError, TypeError, AttributeError) as exc:
        log.warning("Avito resume %s: неожиданный формат (%s)", resume_id, exc)
        return None


# Avito API does not provide an endpoint to list the employer's own vacancies.
# Users must enter vacancy IDs manually (taken from the vacancy URL on avito.ru).
async def get_vacancies(access_token: str, user_id: str) -> list[dict]:
    return []


async def get_chats_for_vacancy(access_token: str, user_id: str, avito_vacancy_id: str) -> list[dict]:
    return await get_applications_for_vacancy(access_token, user_id, avito_vacancy_id)
