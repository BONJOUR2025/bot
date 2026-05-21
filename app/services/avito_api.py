"""Avito Jobs API client."""
import httpx

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
        if r.status_code in (400, 401):
            detail = r.json().get("error_description") or r.json().get("error") or "Ошибка авторизации"
            raise ValueError(f"Авито: {detail}")
        r.raise_for_status()
        return r.json()


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
        return [
            {
                "id": str(v["vacancyId"]),
                "title": v.get("title", ""),
                "area": v.get("locations", [{}])[0].get("name", "") if v.get("locations") else "",
                "url": v.get("url", ""),
            }
            for v in data.get("vacancies", [])
        ]


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
