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
    """Returns active job vacancies for the user."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        params = {"per_page": 50, "page": 1, "status": "active"}
        r = await client.get(
            f"{AVITO_BASE}/job/v2/vacancies",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        if r.status_code == 404:
            return []
        r.raise_for_status()
        data = r.json()
        log.info("Avito vacancies raw keys: %s", list(data.keys()) if isinstance(data, dict) else type(data))
        items = data.get("vacancies") or data.get("items") or data.get("data") or []
        log.info("Avito vacancies count: %d, first item keys: %s",
                 len(items), list(items[0].keys()) if items else [])
        result = []
        for v in items:
            link = v.get("link") or v.get("url") or v.get("vacancyUrl") or ""
            # Extract numeric ID from the URL if no explicit id field
            vid = v.get("vacancyId") or v.get("id") or v.get("vacancy_id") or ""
            if not vid and link:
                # link is like https://www.avito.ru/.../vakansii/title-12345678
                import re
                m = re.search(r"-(\d+)$", link.rstrip("/"))
                vid = m.group(1) if m else link
            addr = v.get("addressDetails") or {}
            area = addr.get("city") or addr.get("district") or addr.get("name") or ""
            result.append({
                "id": str(vid),
                "title": v.get("title") or v.get("name") or "",
                "area": area,
                "url": link,
            })
        return result


async def get_chats_for_vacancy(access_token: str, user_id: str, avito_vacancy_id: str) -> list[dict]:
    """
    Fetch chats (responses) for a specific job vacancy via Avito Messenger API.
    Each chat = one applicant who responded.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        params = {
            "item_ids": avito_vacancy_id,
            "chat_types": "u2i",
            "per_page": 100,
            "page": 1,
        }
        r = await client.get(
            f"{AVITO_BASE}/messenger/v3/chats",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        if r.status_code in (404, 403):
            return []
        r.raise_for_status()
        data = r.json()

        items = []
        for chat in data.get("chats", []):
            chat_id = chat.get("id", "")
            # Find the other user (not us)
            users = chat.get("users", [])
            applicant = next(
                (u for u in users if str(u.get("id")) != str(user_id)),
                users[0] if users else {},
            )
            name = applicant.get("name") or "Кандидат"
            last_msg = chat.get("last_message", {})
            note_text = last_msg.get("content", {}).get("text", "") if last_msg else ""

            items.append({
                "external_id": str(chat_id),
                "name": name,
                "phone": "",
                "email": "",
                "resume_url": "",
                "notes": f"Авито отклик. Сообщение: {note_text}" if note_text else "Авито отклик",
            })

        return items
