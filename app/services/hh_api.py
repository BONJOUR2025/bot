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

            raw_items.append({
                "neg_id": str(neg["id"]),
                "name": name,
                "resume_url": resume_url,
                "resume_id": resume_id,
                "can_view": can_view,
                "age": age,
                "phone": "",
                "email": "",
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
                    contact = full.get("contact") or {}
                    phones = contact.get("phone") or []
                    if phones:
                        p = phones[0]
                        item["phone"] = (
                            p.get("formatted")
                            or f"+{p.get('country','')}{p.get('city','')}{p.get('number','')}"
                        ).strip()
                    item["email"] = contact.get("email") or ""
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
                "name": it["name"],
                "phone": it["phone"],
                "email": it["email"],
                "resume_url": it["resume_url"],
                "age": it["age"],
                "notes": f"Отклик hh.ru: {it['resume_url']}" if it["resume_url"] else "Отклик hh.ru",
            }
            for it in raw_items
        ]

        return {
            "found": data.get("found", 0),
            "pages": data.get("pages", 1),
            "items": items,
        }
