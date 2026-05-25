"""Avito Jobs API client."""
import logging
from datetime import datetime, timedelta

import httpx

log = logging.getLogger(__name__)

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
        })

    return result


# Avito API does not provide an endpoint to list the employer's own vacancies.
# Users must enter vacancy IDs manually (taken from the vacancy URL on avito.ru).
async def get_vacancies(access_token: str, user_id: str) -> list[dict]:
    return []


async def get_chats_for_vacancy(access_token: str, user_id: str, avito_vacancy_id: str) -> list[dict]:
    return await get_applications_for_vacancy(access_token, user_id, avito_vacancy_id)
