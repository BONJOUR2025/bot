"""amoCRM endpoints: status, users (for employee mapping), OAuth bootstrap."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.services.access_control_service import ResolvedUser
from app.services import amo_client

from .dependencies import get_current_user


def create_amo_router() -> APIRouter:
    router = APIRouter(prefix="/amo", tags=["amoCRM"])

    @router.get("/status")
    async def status(current: ResolvedUser = Depends(get_current_user)):
        return {
            "configured": amo_client.is_configured(),
            "authorized": amo_client.is_authorized(),
            "domain": amo_client.get_domain(),
        }

    @router.get("/users")
    async def users(current: ResolvedUser = Depends(get_current_user)):
        try:
            return await amo_client.list_users()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    # ── Diagnostics: raw amoCRM payloads, to verify field shapes ──────
    @router.get("/raw/events")
    async def raw_events(
        date_from: str = Query(..., description="YYYY-MM-DD"),
        date_to: str = Query(..., description="YYYY-MM-DD"),
        limit: int = 50,
        current: ResolvedUser = Depends(get_current_user),
    ):
        """Raw lead_status_changed events for the range (first page) — to check
        the value_after / entity_id / created_at shapes against the code."""
        from datetime import datetime
        try:
            ts_from = int(datetime.strptime(date_from, "%Y-%m-%d").timestamp())
            ts_to = int(datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59).timestamp())
        except ValueError:
            raise HTTPException(status_code=400, detail="Формат даты: YYYY-MM-DD")
        try:
            data = await amo_client.amo_get("/events", params={
                "filter[type]": "lead_status_changed",
                "filter[created_at][from]": ts_from,
                "filter[created_at][to]": ts_to,
                "limit": limit,
            })
            return data.get("_embedded", {}).get("events", data)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @router.get("/raw/lead/{lead_id}")
    async def raw_lead(lead_id: int, current: ResolvedUser = Depends(get_current_user)):
        """Raw lead payload — to verify responsible_user_id / price / pipeline_id / status_id."""
        try:
            return await amo_client.amo_get(f"/leads/{lead_id}")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @router.get("/auth/url")
    async def auth_url(current: ResolvedUser = Depends(get_current_user)):
        if not amo_client.is_configured():
            raise HTTPException(status_code=400, detail="amoCRM не настроен в .env")
        return {"url": amo_client.auth_url()}

    # amoCRM redirects the browser here after consent — no app auth cookie.
    @router.get("/auth/callback", response_class=HTMLResponse)
    async def auth_callback(code: str = Query(...)):
        try:
            await amo_client.exchange_code(code)
        except Exception as exc:
            return HTMLResponse(f"<p>Ошибка авторизации amoCRM: {exc}</p>", status_code=400)
        return HTMLResponse("<p>amoCRM подключён. Можно закрыть вкладку.</p>")

    return router
