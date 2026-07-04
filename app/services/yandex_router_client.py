"""Yandex Router API — road-distance between two GPS points, used to replace
straight-line (haversine) estimates for StarLine NO_SIGNAL gaps with an
actual driving-route length.

Requires YANDEX_ROUTER_API_KEY in .env (Yandex Cloud / Developer Console,
"Router API" product — has a free trial quota, paid beyond that).

Field-shape note: unlike StarLine (validated against a live account in this
codebase), this client's response parsing is written against the publicly
documented Router API v2 shape but has NOT been exercised against a live key
yet — there is no key configured in this project at the time of writing.
_route_distance_km() below uses a resilient/best-effort key search (mirrors
starline_client's _extract_mileage pattern) rather than one strict path, and
get_route_raw() is exposed so the raw payload can be inspected the first
time a real key is used, the same way starline_client's /raw diagnostics work.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from app.settings import settings
from app.utils.logger import get_service_logger

log = get_service_logger("routing")

ROUTER_BASE = "https://api.routing.yandex.net/v2/route"


class YandexRateLimited(RuntimeError):
    """Yandex's own rate limit (HTTP 429) — distinct from a generic failure
    so route_distance_km can back off and retry instead of just giving up
    on the gap."""
    def __init__(self, retry_after: Optional[float] = None):
        self.retry_after = retry_after
        super().__init__("Yandex Router API rate limit exceeded (429)")


def is_configured() -> bool:
    return bool(settings.yandex_router_api_key)


def _retry_after(resp: httpx.Response) -> Optional[float]:
    v = resp.headers.get("Retry-After")
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


async def get_route_raw(lat1: float, lon1: float, lat2: float, lon2: float) -> dict:
    """Raw Router API response for a single two-point route. Real HTTP errors
    (bad key, quota exceeded, no route found) propagate to the caller."""
    if not is_configured():
        raise RuntimeError("Yandex Router API не настроен (нет YANDEX_ROUTER_API_KEY в .env)")
    params = {
        "waypoints": f"{lat1},{lon1}|{lat2},{lon2}",
        "apikey": settings.yandex_router_api_key,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(ROUTER_BASE, params=params)
        if resp.status_code == 429:
            raise YandexRateLimited(_retry_after(resp))
        resp.raise_for_status()
        return resp.json()


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return None


def _find_distance_m(node: Any) -> Optional[float]:
    """Best-effort recursive search for a distance-in-meters field. Router API
    v2 nests it under route.legs[].distance.value; searching broadly rather
    than hardcoding that one path so a minor shape difference (API version,
    account type) doesn't silently break this — same defensive style as
    starline_client._extract_mileage."""
    if isinstance(node, dict):
        dist = node.get("distance")
        if isinstance(dist, dict):
            v = _num(dist.get("value"))
            if v is not None:
                return v
        elif _num(dist) is not None and node.get("value") is None:
            # some shapes put the number directly on "distance"
            v = _num(dist)
            if v is not None:
                return v
        for v in node.values():
            found = _find_distance_m(v)
            if found is not None:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _find_distance_m(v)
            if found is not None:
                return found
    return None


async def route_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[float]:
    """Driving-route distance (km) between two points, or None if the API
    isn't configured, returns no route (after retries), or errors. Never
    raises — callers treat None as "fall back to the straight-line estimate
    for this gap". On a 429, retries a few times honoring Retry-After (or a
    default backoff)."""
    delay = 2.0
    for attempt in range(3):
        try:
            raw = await get_route_raw(lat1, lon1, lat2, lon2)
        except YandexRateLimited as exc:
            wait = exc.retry_after or delay
            log.warning("Yandex Router rate-limited (attempt %d/3), waiting %.1fs", attempt + 1, wait)
            await asyncio.sleep(wait)
            delay *= 2
            continue
        except Exception as exc:
            log.warning("Yandex route_distance_km failed: %s", exc)
            return None
        m = _find_distance_m(raw)
        return round(m / 1000, 2) if m is not None else None
    log.warning("Yandex route_distance_km gave up after repeated rate limiting")
    return None
