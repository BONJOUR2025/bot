"""hh.ru Employer API client."""
import httpx

HH_BASE = "https://api.hh.ru"
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
            f"{HH_BASE}/negotiations/active",
            headers=_headers(access_token),
            params=params,
        )
        if r.status_code == 404:
            return {"found": 0, "items": []}
        r.raise_for_status()
        data = r.json()

        items = []
        for neg in data.get("items", []):
            resume = neg.get("resume") or {}
            contact = resume.get("contact") or {}

            # Extract phone
            phones = contact.get("phone") or []
            phone = ""
            if phones:
                p = phones[0]
                phone = f"+{p.get('country','')}{p.get('city','')}{p.get('number','')}"

            email = contact.get("email") or ""
            name = neg.get("applicant_name") or resume.get("last_name", "")
            resume_url = resume.get("alternate_url") or ""

            items.append({
                "external_id": str(neg["id"]),
                "name": name or "Без имени",
                "phone": phone,
                "email": email,
                "resume_url": resume_url,
                "notes": f"Отклик hh.ru: {resume_url}" if resume_url else "Отклик hh.ru",
            })

        return {
            "found": data.get("found", 0),
            "pages": data.get("pages", 1),
            "items": items,
        }
