"""hh.ru Employer API client."""
import logging
from urllib.parse import urlencode

import httpx

log = logging.getLogger(__name__)

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

        items = []
        first_logged = False
        for neg in data.get("items", []):
            resume = neg.get("resume") or {}

            # Log the first resume structure to help debug what hh.ru actually returns
            if not first_logged:
                log.info("hh.ru resume sample keys: %s", list(resume.keys()))
                contact_sample = resume.get("contact")
                log.info("hh.ru contact sample: %s", contact_sample)
                log.info("hh.ru birthday sample: %s", resume.get("birthday"))
                log.info("hh.ru age field: %s", resume.get("age"))
                first_logged = True

            # ── Phone ──────────────────────────────────────────────
            contact = resume.get("contact") or {}
            phones = contact.get("phone") or []
            phone = ""
            if phones:
                p = phones[0]
                # Prefer pre-formatted string; fallback to assembling from parts
                phone = (
                    p.get("formatted")
                    or f"+{p.get('country', '')}{p.get('city', '')}{p.get('number', '')}"
                ).strip()

            # ── Age ────────────────────────────────────────────────
            age = None
            # 1. Direct age field (int)
            raw_age = resume.get("age")
            if raw_age is not None:
                try:
                    age = int(raw_age)
                except Exception:
                    pass
            # 2. birthday as dict {"year": 1990, "month": 5, "day": 15}
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
                # 3. birthday as ISO string "YYYY-MM-DD"
                elif isinstance(birthday, str) and birthday:
                    try:
                        from datetime import date as _date
                        bday = _date.fromisoformat(birthday[:10])
                        today = _date.today()
                        age = today.year - bday.year - ((today.month, today.day) < (bday.month, bday.day))
                    except Exception:
                        pass

            # ── Name / resume URL ──────────────────────────────────
            email = contact.get("email") or ""
            first = resume.get("first_name") or ""
            last = resume.get("last_name") or ""
            name = (f"{last} {first}".strip()) or neg.get("applicant_name") or "Без имени"
            resume_url = resume.get("alternate_url") or ""

            items.append({
                "external_id": str(neg["id"]),
                "name": name,
                "phone": phone,
                "email": email,
                "resume_url": resume_url,
                "age": age,
                "notes": f"Отклик hh.ru: {resume_url}" if resume_url else "Отклик hh.ru",
            })

        return {
            "found": data.get("found", 0),
            "pages": data.get("pages", 1),
            "items": items,
        }
