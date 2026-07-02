"""StarLine telematics client — used to read a courier car's odometer (пробег).

StarLine's public API (developer.starline.ru) uses a multi-step auth:
  1. app code   : GET id.starline.ru/apiV3/application/getCode  (md5(appId+secret))
  2. app token  : GET id.starline.ru/apiV3/application/getToken (md5(secret+code))
  3. SLID token : POST id.starline.ru/apiV3/user/login          (login + md5(pass))
  4. SLNET token: POST developer.starline.ru/json/v2/auth.slid  → user_id + slnet
Then device data: developer.starline.ru/json/v2/device/{id}/data (position, obd…).

Credentials come from .env: STARLINE_APP_ID, STARLINE_APP_SECRET, STARLINE_LOGIN,
STARLINE_PASSWORD. Everything is best-effort: on any failure the caller gets a
clear error and the courier page falls back to manual odometer entry. Field
shapes vary between accounts/devices, so /courier-salary/starline/* diagnostics
return raw payloads to verify the mapping against a real account.
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Optional

import httpx

from app.settings import settings

log = logging.getLogger(__name__)

ID_BASE = "https://id.starline.ru/apiV3"
DEV_BASE = "https://developer.starline.ru/json"


class StarLineRateLimited(RuntimeError):
    """StarLine's own API rate limit (HTTP 429) — distinct from "no data for
    this device/period" so callers can tell the user to retry shortly instead
    of suggesting a manual entry."""
    def __init__(self, retry_after: Optional[int] = None):
        self.retry_after = retry_after
        super().__init__("StarLine rate limit exceeded (429)")

# Cached session (app token ~4h, slnet token ~ until it 401s).
_session: dict[str, Any] = {"app_token": "", "app_token_ts": 0.0, "slnet": "", "user_id": None}


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def is_configured() -> bool:
    return bool(settings.starline_app_id and settings.starline_app_secret
                and settings.starline_login and settings.starline_password)


async def _get_app_token(client: httpx.AsyncClient) -> str:
    """Steps 1-2: application code → application token (cached ~4h)."""
    if _session["app_token"] and time.time() - _session["app_token_ts"] < 3 * 3600:
        return _session["app_token"]
    app_id, secret = settings.starline_app_id, settings.starline_app_secret
    # getCode: secret = md5(app_secret) (НЕ md5(appId+secret))
    r1 = await client.get(f"{ID_BASE}/application/getCode/",
                          params={"appId": app_id, "secret": _md5(secret)})
    r1.raise_for_status()
    j1 = r1.json()
    code = (j1.get("desc") or {}).get("code")
    if not code:
        raise RuntimeError(f"StarLine getCode: {j1}")
    r2 = await client.get(f"{ID_BASE}/application/getToken/",
                          params={"appId": app_id, "secret": _md5(secret + code)})
    r2.raise_for_status()
    j2 = r2.json()
    token = (j2.get("desc") or {}).get("token")
    if not token:
        raise RuntimeError(f"StarLine getToken: {j2}")
    _session["app_token"], _session["app_token_ts"] = token, time.time()
    return token


async def _auth(client: httpx.AsyncClient) -> tuple[str, Any]:
    """Steps 3-4: SLID user token → SLNET token + user_id. Returns (slnet, user_id)."""
    if _session["slnet"] and _session["user_id"] is not None:
        return _session["slnet"], _session["user_id"]
    app_token = await _get_app_token(client)
    # user login: пароль хешируется sha1
    r3 = await client.post(f"{ID_BASE}/user/login/", params={"token": app_token},
                           data={"login": settings.starline_login, "pass": _sha1(settings.starline_password)})
    r3.raise_for_status()
    j3 = r3.json()
    slid = (j3.get("desc") or {}).get("user_token")
    if not slid:
        raise RuntimeError(f"StarLine login (возможно нужен 2FA/captcha): {j3}")
    r4 = await client.post(f"{DEV_BASE}/v2/auth.slid", json={"slid_token": slid})
    r4.raise_for_status()
    j4 = r4.json()
    slnet = r4.cookies.get("slnet") or j4.get("slnet")
    user_id = j4.get("user_id") or (j4.get("desc") or {}).get("user_id")
    if not slnet or user_id is None:
        raise RuntimeError(f"StarLine auth.slid: {j4}")
    _session["slnet"], _session["user_id"] = slnet, user_id
    return slnet, user_id


def _reset_session() -> None:
    _session.update({"slnet": "", "user_id": None})


async def _authed_get(path: str, params: Optional[dict] = None) -> dict:
    """GET a developer.starline.ru/json path with the SLNET cookie; one re-auth on 401."""
    if not is_configured():
        raise RuntimeError("StarLine не настроен (нет STARLINE_* в .env)")
    async with httpx.AsyncClient(timeout=40) as client:
        slnet, _ = await _auth(client)
        url = f"{DEV_BASE}{path}"
        resp = await client.get(url, params=params, cookies={"slnet": slnet})
        if resp.status_code in (401, 403):
            _reset_session()
            slnet, _ = await _auth(client)
            resp = await client.get(url, params=params, cookies={"slnet": slnet})
        if resp.status_code == 429:
            raise StarLineRateLimited(_retry_after(resp))
        resp.raise_for_status()
        return resp.json()


async def _authed_post(path: str, body: dict) -> dict:
    """POST a developer.starline.ru/json path with the SLNET cookie; re-auth on 401."""
    if not is_configured():
        raise RuntimeError("StarLine не настроен (нет STARLINE_* в .env)")
    async with httpx.AsyncClient(timeout=60) as client:
        slnet, _ = await _auth(client)
        url = f"{DEV_BASE}{path}"
        resp = await client.post(url, json=body, cookies={"slnet": slnet})
        if resp.status_code in (401, 403):
            _reset_session()
            slnet, _ = await _auth(client)
            resp = await client.post(url, json=body, cookies={"slnet": slnet})
        if resp.status_code == 429:
            raise StarLineRateLimited(_retry_after(resp))
        resp.raise_for_status()
        return resp.json()


def _retry_after(resp: httpx.Response) -> Optional[int]:
    v = resp.headers.get("Retry-After")
    try:
        return int(v) if v is not None else None
    except ValueError:
        return None


async def get_status() -> dict:
    return {"configured": is_configured()}


def _ways_body(ts_from: int, ts_to: int) -> dict:
    return {"begin": ts_from, "end": ts_to, "split_way": True, "short_parking": 5,
            "long_parking": 30, "dt_max": 2, "div_days": True, "time_shift": 180,
            "tz": True, "filtering": True}


async def get_ways(device_id: str, ts_from: int, ts_to: int) -> dict:
    """POST /v1/device/{id}/ways — track with mileage for the period."""
    return await _authed_post(f"/v1/device/{device_id}/ways", _ways_body(ts_from, ts_to))


def _ways_mileage(data: Any) -> Optional[float]:
    """Total mileage (km) from a /ways response. Sums per-way mileage if present,
    else falls back to the track-point length.

    StarLine reports mileage in METERS throughout this payload (top-level total
    and each TRACK segment's own "mileage") — convert to km."""
    if not isinstance(data, dict):
        return None
    # explicit total
    for key in ("mileage", "total_mileage", "run", "pofar"):
        v = _num(data.get(key))
        if v is not None and v > 0:
            return round(v / 1000, 1)
    # list of ways/trips, each with its own distance
    ways = data.get("ways") or data.get("data") or data.get("way") or []
    if isinstance(ways, dict):
        ways = ways.get("ways") or ways.get("data") or []
    total = 0.0
    found = False
    for w in ways if isinstance(ways, list) else []:
        if isinstance(w, dict):
            d = _num(w.get("mileage") or w.get("length") or w.get("distance") or w.get("run"))
            if d is not None:
                total += d
                found = True
    if found and total > 0:
        return round(total / 1000, 1)
    # last resort: length of all coordinate points in the payload
    pts = _track_points(data)
    if len(pts) >= 2:
        return round(sum(_haversine_km(pts[i - 1], pts[i]) for i in range(1, len(pts))), 1)
    return None


# A single NO_SIGNAL gap wider than this is almost certainly a bad GPS fix
# (e.g. StarLine sending "null island" 0°,0° or another sentinel as a
# placeholder for "no position"), not the car actually driving that far
# while unreachable — a courier car doesn't teleport hundreds of km between
# two pings. Gaps past this are excluded from the total and reported
# separately so they don't silently blow up the "distance at risk" figure.
NO_SIGNAL_GAP_SANITY_KM = 60.0


def _valid_coord(x: Optional[float], y: Optional[float]) -> bool:
    """Reject missing values and "null island" (0°,0° ± a hair) — a common
    sentinel for "no GPS fix" that some devices/backends send instead of
    omitting the field, which would otherwise register as a huge bogus jump
    from the car's real location to the Gulf of Guinea.

    StarLine's "x"/"y" fields are latitude/longitude respectively (verified
    against real device data — not the "x=lon, y=lat" screen-coordinate
    convention the naming suggests), so the bounds below check x as lat
    (-90..90) and y as lon (-180..180)."""
    if x is None or y is None:
        return False
    if abs(x) < 0.01 and abs(y) < 0.01:
        return False
    return -90 <= x <= 90 and -180 <= y <= 180


def _ways_no_signal_km(data: Any) -> dict:
    """Straight-line distance (km) spanned by NO_SIGNAL gaps in a /ways response.

    A NO_SIGNAL segment always reports mileage=0 (StarLine has no track for that
    stretch, so it doesn't count it towards the total) even when the start/finish
    points are kilometers apart — the car clearly moved, StarLine just doesn't
    know the path. Whether a given gap gets classified as NO_SIGNAL (excluded)
    or as an interpolated TRACK segment (included) can change as StarLine
    reprocesses a still-forming day between calls — this is the actual source
    of the "mileage went down" anomaly, not our arithmetic.

    Individual gaps above NO_SIGNAL_GAP_SANITY_KM (bad fixes, not real driving)
    and gaps with invalid/null-island coordinates are excluded from the sum
    and reported separately in "excluded" — without this, a single corrupt
    point can inflate the "distance at risk" figure by thousands of km."""
    way = data.get("way") if isinstance(data, dict) else None
    if not isinstance(way, list):
        return {"km": 0.0, "gaps": 0, "excluded_count": 0, "excluded_km": 0.0, "top_gaps": []}
    total_km, gaps = 0.0, 0
    excluded_count, excluded_km = 0, 0.0
    all_gaps: list[dict] = []
    for w in way:
        if not isinstance(w, dict) or w.get("type") != "NO_SIGNAL":
            continue
        s, f = w.get("start"), w.get("finish")
        if not isinstance(s, dict) or not isinstance(f, dict):
            continue
        x1, y1, x2, y2 = _num(s.get("x")), _num(s.get("y")), _num(f.get("x")), _num(f.get("y"))
        if not (_valid_coord(x1, y1) and _valid_coord(x2, y2)):
            continue
        # x=lat, y=lon (see _valid_coord) — _haversine_km wants (lon, lat).
        d = _haversine_km((y1, x1), (y2, x2))
        if d <= 0:
            continue
        entry = {"km": round(d, 1), "start": {"t": s.get("t"), "x": x1, "y": y1}, "finish": {"t": f.get("t"), "x": x2, "y": y2}}
        if d > NO_SIGNAL_GAP_SANITY_KM:
            excluded_count += 1
            excluded_km += d
            entry["excluded"] = True
        else:
            total_km += d
            gaps += 1
        all_gaps.append(entry)
    all_gaps.sort(key=lambda g: g["km"], reverse=True)
    return {
        "km": round(total_km, 1), "gaps": gaps,
        "excluded_count": excluded_count, "excluded_km": round(excluded_km, 1),
        "top_gaps": all_gaps[:15],
        # Full list (sane gaps only — excluded/bogus ones are still present but
        # flagged), for callers that want to refine every gap (e.g. road-routing
        # instead of straight-line) rather than just eyeball the top 15.
        "all_gaps": all_gaps,
    }


async def get_ways_mileage(device_id: str, ts_from: int, ts_to: int) -> Optional[float]:
    try:
        return _ways_mileage(await get_ways(device_id, ts_from, ts_to))
    except Exception as exc:
        log.warning("StarLine get_ways_mileage failed: %s", exc)
        return None


async def get_ways_diagnostics(device_id: str, ts_from: int, ts_to: int) -> dict:
    """km + how much distance sits in NO_SIGNAL gaps (excluded from km, but real
    movement) — see _ways_no_signal_km. Never raises; km is None on failure.
    rate_limited/retry_after distinguish StarLine's own 429 from "no data",
    so the caller can tell the user to retry shortly instead of suggesting
    a manual entry."""
    try:
        raw = await get_ways(device_id, ts_from, ts_to)
    except StarLineRateLimited as exc:
        log.warning("StarLine get_ways_diagnostics rate-limited (retry_after=%s)", exc.retry_after)
        return {"km": None, "no_signal_km": 0.0, "no_signal_gaps": 0, "no_signal_excluded_count": 0,
                "no_signal_excluded_km": 0.0, "no_signal_top_gaps": [], "no_signal_all_gaps": [],
                "rate_limited": True, "retry_after": exc.retry_after}
    except Exception as exc:
        log.warning("StarLine get_ways_diagnostics failed: %s", exc)
        return {"km": None, "no_signal_km": 0.0, "no_signal_gaps": 0, "no_signal_excluded_count": 0,
                "no_signal_excluded_km": 0.0, "no_signal_top_gaps": [], "no_signal_all_gaps": [],
                "rate_limited": False, "retry_after": None}
    signal = _ways_no_signal_km(raw)
    return {
        "km": _ways_mileage(raw),
        "no_signal_km": signal["km"], "no_signal_gaps": signal["gaps"],
        "no_signal_excluded_count": signal["excluded_count"], "no_signal_excluded_km": signal["excluded_km"],
        "no_signal_top_gaps": signal["top_gaps"], "no_signal_all_gaps": signal["all_gaps"],
        "rate_limited": False, "retry_after": None,
    }


async def _user_id() -> Any:
    async with httpx.AsyncClient(timeout=40) as client:
        _, uid = await _auth(client)
        return uid


async def get_user_data() -> dict:
    """Raw user payload — devices come with full telemetry here (the per-device
    /device/{id}/data endpoint isn't available on this account)."""
    return await _authed_get(f"/v3/user/{(await _user_id())}/data")


def _devices_from(data: dict) -> list[dict]:
    return (data.get("user_data") or data.get("data") or {}).get("devices") \
        or data.get("devices") or []


def _find_device(data: dict, device_id: str) -> Optional[dict]:
    for d in _devices_from(data):
        if str(d.get("device_id") or d.get("id")) == str(device_id):
            return d
    return None


async def list_devices() -> list[dict]:
    """User's devices: [{device_id, alias, mileage?}]."""
    data = await get_user_data()
    return [{
        "device_id": d.get("device_id") or d.get("id"),
        "alias": d.get("alias") or d.get("name") or "",
        "mileage": _extract_mileage(d),
    } for d in _devices_from(data)]


async def get_device_raw(device_id: str) -> dict:
    """Full device object from user/data (for diagnostics / field mapping)."""
    data = await get_user_data()
    return _find_device(data, device_id) or {"error": "device not found in user/data", "devices_seen": [d.get("device_id") for d in _devices_from(data)]}


def _extract_mileage(node: Any) -> Optional[float]:
    """Pull an odometer/mileage value out of a (nested) StarLine payload, best-effort."""
    if not isinstance(node, dict):
        return None
    for key in ("mileage", "odometer", "mileage_km", "obd_mileage", "run_km", "pofar"):
        v = node.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    for sub in ("obd", "data", "position", "common", "state", "telemetry", "car_state"):
        v = _extract_mileage(node.get(sub))
        if v is not None:
            return v
    return None


async def get_position(device_id: str) -> Optional[dict]:
    """Current GPS point: {ts, lat, lon} from user/data (position.x=lat, y=lon —
    verified against real device data), or None. Used by the background
    poller to build a track for «Маяк» beacons."""
    try:
        dev = _find_device(await get_user_data(), device_id)
        pos = (dev or {}).get("position") or {}
        x, y = _num(pos.get("x")), _num(pos.get("y"))   # x=lat, y=lon
        if x is None or y is None:
            return None
        return {"ts": _num(pos.get("ts")) or 0.0, "lat": x, "lon": y}
    except Exception as exc:
        log.warning("StarLine get_position failed: %s", exc)
        return None


async def get_mileage(device_id: str) -> Optional[float]:
    """Current odometer (km) for a device from user/data, or None if not exposed
    (a «Маяк» beacon has no OBD odometer → None; use the GPS track instead)."""
    try:
        dev = _find_device(await get_user_data(), device_id)
        return _extract_mileage(dev) if dev else None
    except Exception as exc:
        log.warning("StarLine get_mileage failed: %s", exc)
        return None


# ── GPS-track mileage (for beacons without an odometer) ──────────────────────
import math


def _haversine_km(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """Distance between two (lon, lat) points in km."""
    R = 6371.0088
    lat1, lat2 = math.radians(p1[1]), math.radians(p2[1])
    dlat = lat2 - lat1
    dlon = math.radians(p2[0] - p1[0])
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def _num(v: Any) -> Optional[float]:
    """Coerce int/float/str-number to float (StarLine sends coords as strings)."""
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


def _collect_points(node: Any, acc: list[tuple[float, float, float]]) -> None:
    """Recursively gather (ts, lon, lat) from any coordinate-bearing dicts.
    StarLine's own "x"/"y" fields are (lat, lon) — see _valid_coord — while a
    fallback "lat"/"lon"-named payload is already correctly labeled."""
    if isinstance(node, dict):
        if node.get("x") is not None and node.get("y") is not None:
            lat, lon = _num(node.get("x")), _num(node.get("y"))
        else:
            lon, lat = _num(node.get("lon", node.get("lng"))), _num(node.get("lat"))
        if lat is not None and lon is not None:
            ts = _num(node.get("ts") or node.get("t") or node.get("time")) or 0.0
            acc.append((ts, lon, lat))
        for v in node.values():
            _collect_points(v, acc)
    elif isinstance(node, list):
        for v in node:
            _collect_points(v, acc)


def _track_points(data: Any) -> list[tuple[float, float]]:
    """All (lon, lat) points from a StarLine positions/track payload, time-ordered."""
    acc: list[tuple[float, float, float]] = []
    _collect_points(data, acc)
    if any(t for t, _, _ in acc):
        acc.sort(key=lambda p: p[0])
    return [(x, y) for _, x, y in acc]


async def get_track_raw(device_id: str, ts_from: int, ts_to: int) -> dict:
    # This account exposes historical GPS via v1/device/{id}/positions.
    return await _authed_get(f"/v1/device/{device_id}/positions",
                             params={"ts_start": ts_from, "ts_end": ts_to,
                                     "begin": ts_from, "end": ts_to})


async def probe(version: str, device_id: str, action: str, ts_from: int, ts_to: int) -> dict:
    """Diagnostic: try an arbitrary device action so we can find the right one."""
    return await _authed_get(f"/v{version}/device/{device_id}/{action}",
                             params={"ts_start": ts_from, "ts_end": ts_to})


import asyncio

PROBE_ACTIONS = (
    "track", "tracks", "gps", "data", "mileage", "run", "runs", "trip", "trips",
    "ride", "rides", "route", "routes", "history", "way", "stat", "stats",
    "info", "position", "positions", "events", "geofences", "obd", "fuel",
    "motohours", "achievements", "common", "state",
)
PROBE_VERSIONS = ("1", "2", "3")


async def probe_all(device_id: str, ts_from: int, ts_to: int) -> dict:
    """Try a big set of device actions across API versions, concurrently, and
    report which ones actually return data (vs «Not found action»)."""
    try:
        await _user_id()          # warm up auth once before fanning out
    except Exception:
        pass
    sem = asyncio.Semaphore(6)

    async def one(v: str, a: str) -> dict:
        async with sem:
            try:
                r = await probe(v, device_id, a, ts_from, ts_to)
            except Exception as exc:
                return {"version": v, "action": a, "status": "http-error", "detail": str(exc)[:140]}
        if isinstance(r, dict) and r.get("code") == 500 and "Not found action" in str(r.get("codestring")):
            return {"version": v, "action": a, "status": "no-action"}
        if isinstance(r, dict) and isinstance(r.get("code"), int) and r["code"] >= 400:
            return {"version": v, "action": a, "status": "err", "code": r["code"], "codestring": str(r.get("codestring"))[:140]}
        keys = list(r.keys())[:15] if isinstance(r, dict) else None
        return {"version": v, "action": a, "status": "FOUND", "keys": keys}

    results = await asyncio.gather(*[one(v, a) for v in PROBE_VERSIONS for a in PROBE_ACTIONS])
    return {"found": [r for r in results if r["status"] == "FOUND"],
            "errors": [r for r in results if r["status"] in ("err", "http-error")],
            "checked": len(results)}


async def get_track_mileage(device_id: str, ts_from: int, ts_to: int) -> Optional[float]:
    """Sum of the GPS track length (km) over the period, or None if unavailable."""
    try:
        pts = _track_points(await get_track_raw(device_id, ts_from, ts_to))
        if len(pts) < 2:
            return None
        return round(sum(_haversine_km(pts[i - 1], pts[i]) for i in range(1, len(pts))), 1)
    except Exception as exc:
        log.warning("StarLine get_track_mileage failed: %s", exc)
        return None
