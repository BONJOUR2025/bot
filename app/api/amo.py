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
