"""amoCRM HTTP client.

Credentials come from environment / .env (AMO_DOMAIN, AMO_CLIENT_ID,
AMO_CLIENT_SECRET, AMO_REDIRECT_URI, AMO_ACCESS_TOKEN, AMO_REFRESH_TOKEN).
Refreshed tokens are kept in memory and written back to .env so they survive
restarts. Ported from the Msalary sketch and adapted to the main app's config.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import httpx

from app.settings import settings
from app.utils.logger import get_service_logger

log = get_service_logger("amocrm")
ENV_PATH = Path(".env")

# In-memory tokens, seeded from settings; refresh updates these + .env.
_tokens = {
    "access_token": settings.amo_access_token or "",
    "refresh_token": settings.amo_refresh_token or "",
}


def is_configured() -> bool:
    return bool(settings.amo_domain and settings.amo_client_id and settings.amo_client_secret)


def is_authorized() -> bool:
    return bool(_tokens["access_token"])


def get_domain() -> str:
    return settings.amo_domain or ""


def get_access_token() -> str:
    return _tokens["access_token"]


def save_tokens(access_token: str, refresh_token: str) -> None:
    _tokens["access_token"] = access_token
    _tokens["refresh_token"] = refresh_token
    try:
        from dotenv import set_key
        ENV_PATH.touch(exist_ok=True)
        set_key(str(ENV_PATH), "AMO_ACCESS_TOKEN", access_token)
        set_key(str(ENV_PATH), "AMO_REFRESH_TOKEN", refresh_token)
    except Exception as exc:  # persistence is best-effort
        log.warning("amoCRM: failed to persist tokens to .env: %s", exc)


def auth_url() -> str:
    return (
        "https://www.amocrm.ru/oauth?"
        f"client_id={settings.amo_client_id}"
        "&state=salary_calc&mode=popup"
        f"&redirect_uri={settings.amo_redirect_uri}"
    )


async def exchange_code(code: str) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"https://{get_domain()}/oauth2/access_token",
            json={
                "client_id": settings.amo_client_id,
                "client_secret": settings.amo_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.amo_redirect_uri,
            },
        )
    resp.raise_for_status()
    data = resp.json()
    save_tokens(data["access_token"], data["refresh_token"])


async def refresh_tokens() -> bool:
    if not _tokens["refresh_token"]:
        return False
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"https://{get_domain()}/oauth2/access_token",
            json={
                "client_id": settings.amo_client_id,
                "client_secret": settings.amo_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": _tokens["refresh_token"],
                "redirect_uri": settings.amo_redirect_uri,
            },
        )
    if resp.status_code == 200:
        data = resp.json()
        save_tokens(data["access_token"], data["refresh_token"])
        return True
    log.warning("amoCRM: token refresh failed: %s %s", resp.status_code, resp.text[:200])
    return False


async def amo_get(path: str, params: Optional[dict] = None) -> dict:
    """GET amoCRM /api/v4 with one automatic refresh on 401."""
    if not is_configured():
        raise RuntimeError("amoCRM не настроен (нет AMO_DOMAIN/CLIENT_ID/SECRET в .env)")
    if not is_authorized():
        raise RuntimeError("amoCRM не авторизован — пройдите OAuth")
    url = f"https://{get_domain()}/api/v4{path}"
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code == 401:
            if not await refresh_tokens():
                raise RuntimeError("amoCRM: не удалось обновить токен")
            headers["Authorization"] = f"Bearer {get_access_token()}"
            resp = await client.get(url, headers=headers, params=params)
        if resp.status_code == 204:
            return {}
        resp.raise_for_status()
        return resp.json()


async def list_users() -> list[dict]:
    data = await amo_get("/users")
    users = data.get("_embedded", {}).get("users", [])
    return [{"id": u["id"], "name": u.get("name", "")} for u in users]
