"""Split-tunnel VPN: a local headless xray-core proxy plus which of our own
outbound connections (Telegram, Claude API, ...) actually use it.

Happ (the GUI VPN client already on this box) is nothing but a UI shell
around xray-core: the subscription URL it's fed just returns xray-core
config JSON. This module fetches that same subscription directly, runs
xray-core itself under pm2 (same "compiled binary we don't own the source
of" pattern this app already uses for xtunnel — see app/api/system.py's
PM2_STATUS_PROCESSES), and points our own HTTP clients at the local proxy
port it opens — see app/data/vpn_settings_repository.py for the persisted
on/off-per-function state, and app/settings.py's telegram_proxy/claude_proxy
for where each client actually reads its proxy URL from.

Why a separate service from Happ.exe rather than automating the GUI app:
Happ is a GUI (tray icon, window) — running it under pm2 risks it losing
its session/window and behaving unpredictably, whereas xray-core is a
plain console binary built for exactly this (see the plan discussed with
the user before this was built).
"""
from __future__ import annotations

import json
import logging
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx

from app.settings import settings

log = logging.getLogger(__name__)

PM2_PROCESS_NAME = "vpn-proxy"
XRAY_LATEST_RELEASE_API = "https://api.github.com/repos/XTLS/Xray-core/releases/latest"
XRAY_WINDOWS_ASSET = "Xray-windows-64.zip"

# A bare "looks like a VPN client" User-Agent is only enough for the least
# strict providers. Both providers this was tested against actually run a
# device-registration check keyed on more than just UA — without the full
# header set below, they don't error, they silently return a *placeholder*
# profile (valid JSON, valid xray shape, `remarks: "App not supported"`,
# dummy 0.0.0.0 outbound addresses) instead of the real server list. Caught
# by hand: one provider went from 1 fake profile to 17 real ones, the other
# from a 403 antibot challenge to the actual config, once every header below
# was present. X-Hwid is a stable random id (see _device_hwid), not the
# literal value some public writeups use — reusing that exact string would
# make every install running this code look like the same device to a
# provider that watches for it.
SUBSCRIPTION_HEADERS = {
    "User-Agent": "Happ/3.13.0",
    "Accept": "*/*",
    "X-Device-Os": "Android",
    "X-Device-Locale": "ru",
    "X-Device-Model": "SM-A146U",
    "X-Ver-Os": "15",
}


def _device_hwid() -> str:
    """A stable-per-install random id for the X-Hwid header some
    subscription providers require — generated once and cached in
    VpnSettingsRepository rather than hardcoded, so this install doesn't
    share a fingerprint with every other deployment of this same code."""
    from app.data.vpn_settings_repository import get_vpn_settings_repository

    repo = get_vpn_settings_repository()
    hwid = repo.get().get("device_hwid")
    if not hwid:
        import secrets
        hwid = secrets.token_hex(8)
        repo.set_device_hwid(hwid)
    return hwid


class VpnServiceError(RuntimeError):
    """Raised for anything an admin needs to see and act on — message text
    is written to be shown as-is in the Settings UI, not logged-and-hidden."""


def _vpn_dir() -> Path:
    # Absolute: pm2 resolves the script path it's given relative to the
    # CWD it's invoked from (this API process's, not --cwd's), so a
    # relative "vpn\xray.exe" plus --cwd vpn doubled into
    # "vpn\vpn\xray.exe" and pm2 start failed with Script not found —
    # caught in testing before this ever reached production.
    d = Path(settings.vpn_dir).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _xray_exe() -> Path:
    return _vpn_dir() / "xray.exe"


def _config_path() -> Path:
    return _vpn_dir() / "config.json"


# ── Subscription ────────────────────────────────────────────────────────

def fetch_profiles(subscription_url: str) -> list[dict[str, Any]]:
    """GET the subscription and return selectable server profiles:
    [{"remarks": str, "config": <full xray-core JSON config dict>}].

    Subscription response shapes vary across providers/client versions —
    some return a base64 blob of newline-separated vless:// links, this
    provider's panel returns a JSON array of complete, ready-to-run
    xray-core configs (one per server, each with its own inbounds/
    outbounds/routing/dns already filled in). Only that JSON-array shape is
    handled here; a base64-link subscription would need a separate decoder
    nobody has asked for yet — fail with a clear message rather than
    guessing at a different provider's format.
    """
    url = (subscription_url or "").strip()
    if not url:
        raise VpnServiceError("Не задана ссылка на подписку")
    headers = {**SUBSCRIPTION_HEADERS, "X-Hwid": _device_hwid()}
    try:
        resp = httpx.get(url, headers=headers, timeout=20.0, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise VpnServiceError(f"Не удалось обратиться к подписке: {exc}") from exc
    if resp.status_code != 200:
        raise VpnServiceError(
            f"Подписка ответила {resp.status_code}. Если это капча/антибот-страница — "
            f"обычно достаточно повторить запрос: {resp.text[:200]}"
        )
    try:
        data = resp.json()
    except ValueError as exc:
        raise VpnServiceError(
            "Подписка вернула не JSON. Похоже, этот провайдер отдаёт список ссылок "
            "vless://, а не готовый конфиг xray-core — такой формат пока не поддержан."
        ) from exc

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise VpnServiceError("Подписка вернула пустой список серверов")

    profiles: list[dict[str, Any]] = []
    for i, entry in enumerate(data):
        if not isinstance(entry, dict) or not entry.get("outbounds"):
            continue
        remarks = entry.get("remarks") or entry.get("ps") or entry.get("name") or f"Сервер {i + 1}"
        profiles.append({"remarks": str(remarks), "config": entry})
    if not profiles:
        raise VpnServiceError("В подписке не нашлось ни одного распознаваемого профиля")

    # A provider that doesn't like the request often still answers 200 with
    # valid-shaped JSON — a single placeholder profile with a dummy
    # 0.0.0.0-address outbound and remarks like "App not supported" —
    # rather than an error. Surface that as a real error instead of letting
    # an obviously-fake server sit in the picker looking like a real choice.
    real = [p for p in profiles if not _looks_like_placeholder(p["config"])]
    if not real:
        raise VpnServiceError(
            f'Подписка ответила, но без рабочих серверов (профиль «{profiles[0]["remarks"]}» — '
            "похоже на служебную заглушку). Этому провайдеру нужны другие заголовки запроса, "
            "которых мы ещё не подобрали."
        )
    return real


def _looks_like_placeholder(config: dict[str, Any]) -> bool:
    """True if every proxy outbound in this profile points at 0.0.0.0 (or
    has no address at all) — the shape a provider serves back when it
    rejected the request but still wants to answer 200 with something
    parseable, rather than a real server."""
    proxy_outbounds = [o for o in (config.get("outbounds") or []) if o.get("protocol") not in ("freedom", "blackhole")]
    if not proxy_outbounds:
        return True
    for outbound in proxy_outbounds:
        vnext = (outbound.get("settings") or {}).get("vnext") or []
        addresses = {str(v.get("address") or "") for v in vnext}
        if addresses - {"", "0.0.0.0", "127.0.0.1"}:
            return False
    return True


def _extract_local_proxies(config: dict[str, Any]) -> tuple[str, str | None]:
    """(socks_proxy_url, http_proxy_url) read from the profile's own
    `inbounds` — trust what the subscription says to listen on rather than
    hardcoding the ports one provider happened to use, since a different
    provider or a future refresh of the same one could pick different ones."""
    socks_url: str | None = None
    http_url: str | None = None
    for inbound in config.get("inbounds") or []:
        protocol = inbound.get("protocol")
        listen = inbound.get("listen") or "127.0.0.1"
        port = inbound.get("port")
        if not port:
            continue
        if protocol == "socks" and socks_url is None:
            socks_url = f"socks5://{listen}:{port}"
        elif protocol == "http" and http_url is None:
            http_url = f"http://{listen}:{port}"
    if socks_url is None:
        raise VpnServiceError("В выбранном профиле нет локального socks-инбаунда — адрес прокси неизвестен")
    return socks_url, http_url


# ── xray-core binary ────────────────────────────────────────────────────

def ensure_xray_binary() -> Path:
    """Download+unzip the official XTLS/Xray-core Windows release if it's
    not already present. Idempotent — safe to call before every profile
    apply, cheap when the binary already exists (a single stat)."""
    exe = _xray_exe()
    if exe.exists():
        return exe

    log.info("Скачиваю xray-core (первый запуск сплит-туннеля)...")
    try:
        meta = httpx.get(XRAY_LATEST_RELEASE_API, timeout=20.0).json()
        asset = next(a for a in meta.get("assets", []) if a.get("name") == XRAY_WINDOWS_ASSET)
        zip_resp = httpx.get(asset["browser_download_url"], timeout=120.0, follow_redirects=True)
        zip_resp.raise_for_status()
    except Exception as exc:
        raise VpnServiceError(f"Не удалось скачать xray-core: {exc}") from exc

    try:
        with zipfile.ZipFile(BytesIO(zip_resp.content)) as zf:
            zf.extractall(_vpn_dir())
    except Exception as exc:
        raise VpnServiceError(f"Не удалось распаковать xray-core: {exc}") from exc

    if not exe.exists():
        raise VpnServiceError("Архив xray-core распакован, но xray.exe не найден внутри")
    return exe


# ── pm2 lifecycle for the proxy process ────────────────────────────────

def _pm2_jlist() -> list[dict]:
    try:
        result = subprocess.run(
            ["pm2", "jlist"], shell=True, capture_output=True,
            encoding="utf-8", errors="replace", timeout=15,
        )
        return json.loads(result.stdout)
    except Exception:
        return []


def restart_proxy_process() -> None:
    """Start the pm2 process the first time, restart it on every later
    call (picking up a just-rewritten config.json) — same "create on
    deploy.ps1 if missing" idiom as bot-warmer there."""
    exe = ensure_xray_binary()
    exists = any(p.get("name") == PM2_PROCESS_NAME for p in _pm2_jlist())
    try:
        if exists:
            subprocess.run(["pm2", "restart", PM2_PROCESS_NAME], shell=True, check=True,
                            capture_output=True, timeout=20)
        else:
            subprocess.run(
                ["pm2", "start", str(exe), "--name", PM2_PROCESS_NAME, "--cwd", str(_vpn_dir()),
                 "--", "run", "-c", str(_config_path())],
                shell=True, check=True, capture_output=True, timeout=20,
            )
        subprocess.run(["pm2", "save"], shell=True, capture_output=True, timeout=15)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode("utf-8", "replace")
        raise VpnServiceError(f"pm2 не смог запустить/перезапустить прокси: {stderr[:300]}") from exc


# ── Applying a chosen profile ───────────────────────────────────────────

def apply_profile(config: dict[str, Any]) -> dict[str, str | None]:
    """Write `config` as xray-core's config.json and (re)start the proxy
    process under it. Returns {"socks_proxy": ..., "http_proxy": ...} for
    the caller to persist via VpnSettingsRepository.set_active_profile."""
    socks_proxy, http_proxy = _extract_local_proxies(config)
    with open(_config_path(), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    restart_proxy_process()
    return {"socks_proxy": socks_proxy, "http_proxy": http_proxy}


# ── Wiring the split into our own processes ────────────────────────────

def sync_env_proxy_vars() -> dict[str, bool]:
    """Write TELEGRAM_PROXY/CLAUDE_PROXY into .env to match the saved
    route flags (blank when a function's toggle is off or no server is
    selected yet). Does NOT restart telegram_bot/api_server — those cache
    the value in the settings singleton at process start, same as every
    other .env-backed setting in this app, so the caller must still hit the
    existing POST /system/process-status/{name}/restart for the change to
    take effect. Returns {"telegram": changed, "claude": changed} so the
    caller/UI knows which processes actually need that restart.
    """
    from dotenv import set_key
    from app.data.vpn_settings_repository import get_vpn_settings_repository

    repo = get_vpn_settings_repository()
    doc = repo.get()
    socks = repo.socks_proxy_url()

    env_path = Path(".env")
    changed = {}
    for key, env_name in (("telegram", "TELEGRAM_PROXY"), ("claude", "CLAUDE_PROXY")):
        want = socks if doc["route"].get(key) and socks else ""
        current = getattr(settings, f"{key}_proxy", None) or ""
        changed[key] = want != current
        try:
            set_key(str(env_path), env_name, want)
        except Exception as exc:
            log.warning("Не удалось записать %s в .env: %s", env_name, exc)
    return changed
