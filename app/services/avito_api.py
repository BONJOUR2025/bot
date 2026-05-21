"""Avito Jobs API client."""
import logging

import httpx

log = logging.getLogger(__name__)

AVITO_BASE = "https://api.avito.ru"
TIMEOUT = 15.0


async def get_token(client_id: str, client_secret: str) -> dict:
    """
    OAuth2 client_credentials flow.
    Returns {"access_token": str, "expires_in": int}
    or raises ValueError.
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
    """Returns {"user_id": str, "name": str}"""
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


async def get_vacancies(access_token: str, user_id: str) -> list[dict]:
    """Returns active job vacancies for the authenticated employer via Items API."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        params = {"per_page": 50, "page": 1}
        r = await client.get(
            f"{AVITO_BASE}/core/v1/items",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        if r.status_code == 404:
            return []
        r.raise_for_status()
        data = r.json()
        log.info("Avito items raw keys=%s raw=%s", list(data.keys()) if isinstance(data, dict) else type(data), str(data)[:500])
        resources = data.get("resources") or data.get("items") or data.get("data") or []
        log.info("Avito items count=%d, first keys=%s",
                 len(resources), list(resources[0].keys()) if resources else [])
        result = []
        for v in resources:
            cat = v.get("category") or {}
            cat_name = cat.get("name") or "" if isinstance(cat, dict) else ""
            # Only include job vacancies (skip regular ads)
            if cat_name and "ванси" not in cat_name.lower() and "работ" not in cat_name.lower():
                continue
            vid = str(v.get("id") or "")
            title = v.get("title") or v.get("name") or ""
            address = v.get("address") or ""
            url = v.get("url") or v.get("link") or ""
            if not url and vid:
                url = f"https://www.avito.ru/items/{vid}"
            result.append({
                "id": vid,
                "title": title,
                "area": address,
                "url": url,
            })
        return result


async def get_applications_for_vacancy(access_token: str, user_id: str, avito_vacancy_id: str) -> list[dict]:
    """
    Fetch job applications for a specific vacancy via Avito Jobs API v1.
    Returns list of candidates who applied.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        params = {"vacancy_id": avito_vacancy_id, "per_page": 100, "page": 1}
        r = await client.get(
            f"{AVITO_BASE}/job/v1/applications",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        if r.status_code in (404, 403):
            return []
        r.raise_for_status()
        data = r.json()
        log.info("Avito applications raw keys: %s", list(data.keys()) if isinstance(data, dict) else type(data))

        items = []
        applications = data.get("applications") or data.get("items") or data.get("data") or []
        log.info("Avito applications count: %d, first keys: %s",
                 len(applications), list(applications[0].keys()) if applications else [])
        for app in applications:
            app_id = str(app.get("id") or app.get("application_id") or "")
            applicant = app.get("applicant") or app.get("user") or app.get("candidate") or {}
            name = (
                applicant.get("name")
                or applicant.get("fullName")
                or app.get("name")
                or "Кандидат"
            )
            phone = applicant.get("phone") or app.get("phone") or ""
            email = applicant.get("email") or app.get("email") or ""
            resume_url = app.get("resume_url") or app.get("resumeUrl") or ""
            cover = app.get("cover_letter") or app.get("coverLetter") or app.get("message") or ""
            items.append({
                "external_id": app_id,
                "name": name,
                "phone": phone,
                "email": email,
                "resume_url": resume_url,
                "notes": f"Авито отклик. {cover}" if cover else "Авито отклик",
            })

        return items


# Keep legacy alias for backwards compatibility during migration
async def get_chats_for_vacancy(access_token: str, user_id: str, avito_vacancy_id: str) -> list[dict]:
    return await get_applications_for_vacancy(access_token, user_id, avito_vacancy_id)
