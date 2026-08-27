"""API for split-tunnel VPN settings — subscription URL, server selection,
and which of our own pm2 processes use the local xray-core proxy.
See app/services/vpn_service.py and app/data/vpn_settings_repository.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .dependencies import require_permission


def _routable_processes() -> dict[str, str]:
    """{process_key: label} for every pm2 process it makes sense to route
    through the VPN — the whole fleet minus the compiled binaries
    (PM2_STATUS_PROCESSES: xtunnel, vpn_proxy itself) that have no
    heartbeat and no HTTP client of ours to route in the first place.
    Sourced straight from app.api.system's fleet registry rather than a
    second hardcoded list here — a process added there becomes routable
    with no change in this file.
    """
    from app.api.system import PROCESS_LABELS, PM2_STATUS_PROCESSES

    return {k: v for k, v in PROCESS_LABELS.items() if k not in PM2_STATUS_PROCESSES}


class SubscriptionInput(BaseModel):
    url: str


class ProfileInput(BaseModel):
    remarks: str


class RouteInput(BaseModel):
    route: dict[str, bool]


def create_vpn_router() -> APIRouter:
    router = APIRouter(
        prefix="/vpn",
        tags=["VPN"],
        dependencies=[Depends(require_permission("settings"))],
    )

    @router.get("/settings")
    async def get_settings():
        from app.data.vpn_settings_repository import get_vpn_settings_repository

        doc = get_vpn_settings_repository().get()
        return {**doc, "routable_processes": _routable_processes()}

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
        process under it. Any process already toggled on gets re-synced
        too — a server switch can change the local proxy port, and a
        process still pointed at the old one would silently go nowhere."""
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

        restarting = await _resync_active_routes(repo)
        return {"active_profile": repo.get()["active_profile"], "restarting": restarting}

    @router.put("/route")
    async def set_route(data: RouteInput):
        """Toggle which pm2 processes go through the proxy. Each changed
        process is restarted immediately (detached, doesn't block this
        request even for api_server restarting itself) with its
        HTTP(S)_PROXY/ALL_PROXY set or cleared — see
        vpn_service.sync_process_proxy. `restarting` in the response lists
        which processes the UI should show as "restarting…" for the next
        few seconds."""
        import asyncio
        from app.services import vpn_service
        from app.api.system import PROCESS_TO_PM2

        routable = _routable_processes()
        unknown = [k for k in data.route if k not in routable]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Неизвестный процесс: {', '.join(unknown)}")

        from app.data.vpn_settings_repository import get_vpn_settings_repository
        repo = get_vpn_settings_repository()
        before = repo.get()["route"]
        changed = {k: v for k, v in data.route.items() if bool(before.get(k)) != bool(v)}
        repo.set_route(data.route)

        for key, want in changed.items():
            await asyncio.to_thread(
                vpn_service.sync_process_proxy, PROCESS_TO_PM2[key], key, routable[key], "heartbeat", want,
            )
        return {"route": repo.get()["route"], "restarting": list(changed)}

    async def _resync_active_routes(repo) -> list[str]:
        import asyncio
        from app.services import vpn_service
        from app.api.system import PROCESS_TO_PM2

        routable = _routable_processes()
        on = [k for k, v in repo.get()["route"].items() if v and k in routable]
        for key in on:
            await asyncio.to_thread(
                vpn_service.sync_process_proxy, PROCESS_TO_PM2[key], key, routable[key], "heartbeat", True,
            )
        return on

    return router
