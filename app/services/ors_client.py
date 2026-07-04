"""OpenRouteService (openrouteservice.org) — road-distance between two GPS
points, used as an alternative to Yandex Router API for refining StarLine
NO_SIGNAL gaps from a straight-line estimate to an actual driving-route
length.

Requires ORS_API_KEY in .env (openrouteservice.org account, free-tier key —
historically published as ~2000 requests/day / 40/min on their public API;
verify current limits on their site, they can change). ORS is open-source
(OpenStreetMap-based) and self-hostable if the hosted free tier isn't enough.

Field-shape note: same caveat as yandex_router_client — this parsing follows
the publicly documented Directions API v2 response shape but hasn't been
exercised against a live key in this project. get_route_raw() is exposed so
the payload can be inspected the first time a real key is used."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from app.settings import settings
from app.utils.logger import get_service_logger

log = get_service_logger("routing")

# Driving profile suits a courier car; ORS also has cycling/walking/etc.
ORS_BASE = "https://api.openrouteservice.org/v2/directions/driving-car"


class ORSRateLimited(RuntimeError):
    """ORS's own per-minute quota (HTTP 429) — distinct from a generic
    failure so route_distance_km can back off and retry instead of just
    giving up on the gap."""
    def __init__(self, retry_after: Optional[float] = None):
        self.retry_after = retry_after
        super().__init__("OpenRouteService rate limit exceeded (429)")


def is_configured() -> bool:
    return bool(settings.ors_api_key)


def _retry_after(resp: httpx.Response) -> Optional[float]:
    v = resp.headers.get("Retry-After")
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


async def get_route_raw(lat1: float, lon1: float, lat2: float, lon2: float) -> dict:
    """Raw ORS Directions API response for a single two-point route (GeoJSON).
    Real HTTP errors (bad key, quota exceeded, no route found) propagate."""
    if not is_configured():
        raise RuntimeError("OpenRouteService не настроен (нет ORS_API_KEY в .env)")
    # ORS wants [lon, lat] pairs, not [lat, lon].
    # radiuses=-1 (no limit) lets it snap to the nearest road however far —
    # NO_SIGNAL gap endpoints are exactly where a courier stopped (courtyard,
    # parking lot, under a roof), so the default ~350m search often finds
    # nothing (ORS error 2010) even though a real nearby road exists.
    body = {"coordinates": [[lon1, lat1], [lon2, lat2]], "radiuses": [-1, -1]}
    headers = {"Authorization": settings.ors_api_key, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(ORS_BASE, json=body, headers=headers)
        if resp.status_code == 429:
            raise ORSRateLimited(_retry_after(resp))
        if resp.status_code >= 400:
            # ORS puts the actual reason (e.g. "no routable point near
            # coordinate", bad/missing key, wrong plan) in the JSON body —
            # httpx's own message just says "404 Not Found" with no detail.
            raise RuntimeError(f"ORS {resp.status_code}: {resp.text[:500]}")
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
    """Best-effort recursive search for a distance-in-meters field. The
    documented shape nests it under features[0].properties.summary.distance
    (GeoJSON response); searching broadly rather than hardcoding that one
    path, same defensive style as starline_client._extract_mileage and
    yandex_router_client._find_distance_m."""
    if isinstance(node, dict):
        summary = node.get("summary")
        if isinstance(summary, dict):
            v = _num(summary.get("distance"))
            if v is not None:
                return v
        v = _num(node.get("distance"))
        if v is not None and not isinstance(node.get("distance"), dict):
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
    default backoff) — a burst of gaps easily outruns ORS's free-tier
    per-minute quota even with the caller's own pacing, so a couple of
    retries here meaningfully cuts how many gaps silently fall back."""
    delay = 2.0
    for attempt in range(3):
        try:
            raw = await get_route_raw(lat1, lon1, lat2, lon2)
        except ORSRateLimited as exc:
            wait = exc.retry_after or delay
            log.warning("ORS rate-limited (attempt %d/3), waiting %.1fs", attempt + 1, wait)
            await asyncio.sleep(wait)
            delay *= 2
            continue
        except Exception as exc:
            log.warning("ORS route_distance_km failed: %s", exc)
            return None
        m = _find_distance_m(raw)
        return round(m / 1000, 2) if m is not None else None
    log.warning("ORS route_distance_km gave up after repeated rate limiting")
    return None
