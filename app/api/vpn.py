"""API for split-tunnel VPN settings — subscription URL, server selection,
and which of our own outbound connections use the local xray-core proxy.
See app/services/vpn_service.py and app/data/vpn_settings_repository.py.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .dependencies import require_permission


class SubscriptionInput(BaseModel):
    url: str


class ProfileInput(BaseModel):
    remarks: str


class RouteInput(BaseModel):
    telegram: Optional[bool] = None
    claude: Optional[bool] = None


def create_vpn_router() -> APIRouter:
    router = APIRouter(
        prefix="/vpn",
        tags=["VPN"],
        dependencies=[Depends(require_permission("settings"))],
    )

    @router.get("/settings")
    async def get_settings():
        from app.data.vpn_settings_repository import ROUTABLE_FUNCTIONS, get_vpn_settings_repository

        doc = get_vpn_settings_repository().get()
        return {**doc, "routable_functions": ROUTABLE_FUNCTIONS}

    @router.post("/subscription")
    async def set_subscription(data: SubscriptionInput):
        """Save the subscription URL and return the servers it currently
        offers — does NOT apply one yet, that's a separate explicit step
        (POST /vpn/profile) so switching servers later doesn't require
        re-pasting the URL."""
        import asyncio
        from app.services import vpn_service
        from app.data.vpn_settings_repository import get_vpn_settings_repository

        try:
            profiles = await asyncio.to_thread(vpn_service.fetch_profiles, data.url)
        except vpn_service.VpnServiceError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        get_vpn_settings_repository().set_subscription_url(data.url)
        return {"profiles": [{"remarks": p["remarks"]} for p in profiles]}

    @router.get("/profiles")
    async def list_profiles():
        """Re-fetch the already-saved subscription's current server list —
        used to refresh the picker (a provider's node list can change)
        without asking the admin to paste the URL again."""
        import asyncio
        from app.services import vpn_service
        from app.data.vpn_settings_repository import get_vpn_settings_repository

        url = get_vpn_settings_repository().get()["subscription_url"]
        if not url:
            raise HTTPException(status_code=400, detail="Подписка ещё не задана")
        try:
            profiles = await asyncio.to_thread(vpn_service.fetch_profiles, url)
        except vpn_service.VpnServiceError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"profiles": [{"remarks": p["remarks"]} for p in profiles]}

    @router.post("/profile")
    async def select_profile(data: ProfileInput):
        """Fetch the subscription fresh, pick the profile matching
        `remarks`, write it as xray-core's config and (re)start the proxy
        process under it."""
        import asyncio
        from app.services import vpn_service
        from app.data.vpn_settings_repository import get_vpn_settings_repository

        repo = get_vpn_settings_repository()
        url = repo.get()["subscription_url"]
        if not url:
            raise HTTPException(status_code=400, detail="Подписка ещё не задана")
        try:
            profiles = await asyncio.to_thread(vpn_service.fetch_profiles, url)
            match = next((p for p in profiles if p["remarks"] == data.remarks), None)
            if match is None:
                raise HTTPException(status_code=404, detail=f'Сервер «{data.remarks}» не найден в подписке')
            proxies = await asyncio.to_thread(vpn_service.apply_profile, match["config"])
        except vpn_service.VpnServiceError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        repo.set_active_profile(data.remarks, proxies["socks_proxy"], proxies.get("http_proxy"))
        changed = await asyncio.to_thread(vpn_service.sync_env_proxy_vars)
        return {"active_profile": repo.get()["active_profile"],
                "restart_needed": [k for k, v in changed.items() if v]}

    @router.put("/route")
    async def set_route(data: RouteInput):
        """Toggle which functions go through the proxy. Takes effect for a
        function only after its process is restarted — see
        vpn_service.sync_env_proxy_vars' docstring for why that can't be
        avoided; restart_needed in the response tells the UI which of
        POST /system/process-status/{telegram_bot,api_server}/restart to
        offer."""
        import asyncio
        from app.services import vpn_service
        from app.data.vpn_settings_repository import get_vpn_settings_repository

        flags = {k: v for k, v in data.model_dump().items() if v is not None}
        repo = get_vpn_settings_repository()
        repo.set_route(flags)
        changed = await asyncio.to_thread(vpn_service.sync_env_proxy_vars)
        return {"route": repo.get()["route"], "restart_needed": [k for k, v in changed.items() if v]}

    return router
