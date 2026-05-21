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
    """Returns active job vacancies for the authenticated employer."""
    import re
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        params = {"per_page": 50, "page": 1, "status": "active", "user_id": user_id}
        r = await client.get(
            f"{AVITO_BASE}/job/v2/vacancies",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        if r.status_code == 404:
            return []
        r.raise_for_status()
        data = r.json()
        items = data.get("vacancies") or data.get("items") or data.get("data") or []
        log.info("Avito vacancies count=%d user_id=%s companies=%s",
                 len(items),
                 user_id,
                 list({v.get("companyName") or v.get("company") for v in items[:5]}))
        result = []
        for v in items:
            link = v.get("url") or v.get("link") or v.get("vacancyUrl") or ""
            vid = v.get("id") or v.get("vacancyId") or v.get("vacancy_id") or ""
            if not vid and link:
                m = re.search(r"-(\d+)$", link.rstrip("/"))
                vid = m.group(1) if m else link
            addr = v.get("address") or v.get("addressDetails") or {}
            if isinstance(addr, dict):
                area = addr.get("city") or addr.get("district") or addr.get("name") or ""
            else:
                area = str(addr) if addr else ""
            result.append({
                "id": str(vid),
                "title": v.get("title") or v.get("name") or "",
                "area": area,
                "url": link,
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
