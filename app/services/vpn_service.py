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

import ipaddress
import json
import logging
import socket
import subprocess
import time
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


def extract_proxy_outbound(config: dict[str, Any]) -> dict[str, Any]:
    """Pull just the proxy server's own outbound object (not the profile's
    freedom/blackhole ones) out of a full xray-core profile config, tagged
    "proxy" — reused as-is to build the separate TUN config below, so a
    server switch doesn't need to re-fetch the subscription a second time."""
    for outbound in config.get("outbounds") or []:
        if outbound.get("protocol") not in ("freedom", "blackhole"):
            out = dict(outbound)
            out["tag"] = "proxy"
            return out
    raise VpnServiceError("В профиле не найден outbound прокси-сервера")


# ── TUN mode: routing ANY OS process (browser, third-party apps — not just
# our own pm2 fleet) through the VPN ────────────────────────────────────
#
# The SOCKS/HTTP proxy above only helps a process that already knows to use
# a proxy (our own httpx/requests-based services). A browser or an unrelated
# third-party exe generally doesn't — and it can't be retrofitted by setting
# an env var, since it's already running and wasn't started by us. xray-core
# has a "tun" inbound (uses the same wintun.dll already sitting next to
# xray.exe) that captures the machine's own default route and re-emits
# "direct" traffic itself, plus a routing rule type ("process") that matches
# by the OS process issuing the connection — so instead of asking each app
# to cooperate, we intercept everything and only steer the processes an
# admin explicitly picked into the "proxy" outbound; everything else falls
# through with no matching rule to outbounds[0] ("direct"/freedom), which is
# xray's documented behavior for unmatched traffic — i.e. safe-by-default:
# nothing is captured into the VPN unless a process was explicitly added.
#
# This has to run as a genuinely separate, elevated Windows Scheduled Task
# rather than another pm2 process: creating a TUN network adapter needs an
# admin token, and pm2 itself runs as this (non-elevated) Windows user —
# a pm2-spawned child can't silently grant itself that. The task is
# registered once (by an administrator — see docs/vpn_tun_setup, done as
# part of building this feature) with a trigger that never fires on its
# own (a one-time date far in the future); `schtasks /run`/`/end`/`/query`
# — which do NOT need the caller to be elevated once the task itself is
# registered at "highest" privileges — are all bot-app (non-elevated) ever
# calls at runtime. If the task isn't registered yet, /run fails with a
# clear "task not found" error rather than silently trying to self-elevate.
TUN_TASK_NAME = "BonjourVpnTun"


def _tun_config_path() -> Path:
    return _vpn_dir() / "config-tun.json"


def _tun_log_path() -> Path:
    return _vpn_dir() / "tun.log"


def _tun_script_path() -> Path:
    return _vpn_dir() / "tun_run.ps1"


def build_tun_config(proxy_outbound: dict[str, Any], process_paths: list[str]) -> dict[str, Any]:
    # Xray's process matcher keys off whether the string contains a "/" to
    # decide name vs. absolute-path vs. folder mode, and the docs call out
    # Windows specifically for needing "/" instead of "\" — our paths come
    # from PowerShell's Get-Process (backslashes), so normalize here rather
    # than relying on every caller to remember to.
    normalized = [p.replace("\\", "/") for p in process_paths]
    rules = [{"type": "field", "process": normalized, "outboundTag": "proxy"}] if normalized else []
    return {
        # "access": "none" turns off the per-connection access log (the
        # "from udp:... accepted ... [direct]" lines) — separate from
        # loglevel, which only governs [Warning]/[Info]/[Error] system
        # messages and doesn't touch these. Without it: this adapter gets
        # an APIPA (169.254.x.x) address regardless of the "gateway"
        # setting below (confirmed by hand — Get-NetIPAddress showed
        # 169.254.191.101 even with an explicit gateway configured), and
        # Windows' own NetBIOS self-announcement for that address retries
        # in a tight loop nothing ever answers — tens of thousands of
        # access-log lines a minute, multiple MB of tun.log inside two
        # minutes. Harmless to routing, just noisy; this is the fix for
        # the noise that doesn't risk breaking routing the way excluding
        # 169.254.0.0/16 from autoSystemRoutingTable did.
        "log": {"loglevel": "warning", "access": "none"},
        "inbounds": [{
            "port": 0,
            "protocol": "tun",
            "settings": {
                "name": "BonjourVpnTun",
                "desc": "Wintun",
                "mtu": 1500,
                # Without this, Windows leaves the adapter unaddressed and
                # assigns it an APIPA (169.254.0.0/16) address itself — which
                # then makes Windows' own NetBIOS name-registration announce
                # itself in a tight, unthrottled retry loop (no real segment
                # ever answers it), seen as tens of thousands of
                # udp:169.254.x.x:137 lines a minute in tun.log and mistaken
                # at first for a routing loop. A real point-to-point address
                # avoids the APIPA fallback entirely.
                "gateway": ["10.90.0.1/30", "fc00:bonjour::1/64"],
                # Capture the whole default route — required for process
                # matching to see traffic that was never pointed at a proxy
                # in the first place, not just our own httpx clients. Per
                # Xray's own proxy/tun/README: "You can't just route
                # 0.0.0.0/0 through xray0 ... that will result Xray-core
                # itself try to reach its uplink through xray0 interface,
                # resulting infinite network loop" — start_tun() below adds
                # the documented fix (a host route to the proxy server
                # itself via the real gateway) before this ever starts.
                # A literal "0.0.0.0/0" here, specifically — swapping it for
                # a computed list of equivalent-but-narrower CIDR blocks
                # (tried, to exclude 169.254.0.0/16 and quiet down noisy-but-
                # harmless APIPA broadcast logging) silently stopped Xray
                # from installing ANY system route at all: `route print`
                # with this active showed nothing for BonjourVpnTun, no
                # traffic reached it, routing simply didn't happen. Xray's
                # "become the default route" handling apparently keys off
                # this exact literal value rather than prefix coverage —
                # caught by hand, so noisy-log-but-working beats quiet-but-
                # broken here.
                "autoSystemRoutingTable": ["0.0.0.0/0", "::/0"],
            },
        }],
        "outbounds": [_bind_to_physical_nic({"protocol": "freedom", "tag": "direct"}), _bind_to_physical_nic(proxy_outbound)],
        "routing": {"domainStrategy": "AsIs", "rules": rules},
    }


def _bind_to_physical_nic(outbound: dict[str, Any]) -> dict[str, Any]:
    """Bind an outbound's egress to the real physical NIC's own local IP
    (xray's "sendThrough" — a plain OutboundObject field, forces the OS to
    route that outbound's own sockets via whichever interface owns that
    address) rather than letting it follow the ambient default route —
    which, once start_tun installs a route through BonjourVpnTun itself
    (see _install_default_route), IS that same TUN adapter. Without this,
    "direct" traffic loops back into the very adapter it was trying to
    leave through — caught by hand when xtunnel (not one of the routed
    processes, should've gone straight out via freedom) got stuck in
    "Connecting" the moment our TUN route went live. The host-route
    exclusion added separately for the proxy server's own IP predates
    this and stays as a second, independent safety net — this fixes the
    same root problem for every "direct" destination, not just that one.
    """
    local_ip = _physical_local_ip()
    if not local_ip:
        return outbound
    return {**outbound, "sendThrough": local_ip}


def _physical_local_ip() -> str | None:
    """The real physical NIC's own IPv4 address, for _bind_to_physical_nic."""
    script = (
        f"(Get-NetIPAddress -InterfaceAlias '{settings.vpn_tun_outbound_interface}' "
        "-AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -First 1).IPAddress"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=15,
    )
    ip = result.stdout.strip()
    return ip or None


def _write_tun_config(proxy_outbound: dict[str, Any], process_paths: list[str]) -> None:
    config = build_tun_config(proxy_outbound, process_paths)
    with open(_tun_config_path(), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _tun_settings_path() -> Path:
    return Path(settings.vpn_settings_file).resolve()


def _ensure_tun_script() -> Path:
    """The task's actual action — self-sufficient rather than a thin
    wrapper the Python side has to babysit, because it also has to work
    unattended right after a boot (see register_tun_task's at-startup
    trigger), when nothing of ours has run yet to call start_tun():
      1. Checks vpn_settings.json's own "tun_enabled" flag first and exits
         immediately if it's false — so a reboot after an explicit
         "Выключить" stays off instead of the task's mere existence
         silently turning system-wide capture back on every time.
      2. Kicks off a background job that waits for the adapter to appear
         and installs the default route through it — the same fix
         start_tun() used to do itself over the API, moved here so it
         also runs on a cold boot before bot-app is even listening.
      3. Runs xray in the foreground as before, streaming to tun.log.
    """
    exe = ensure_xray_binary()
    script = _tun_script_path()
    script.write_text(
        f"$cfg = $null\n"
        f'try {{ $cfg = Get-Content -Raw -Path "{_tun_settings_path()}" -Encoding UTF8 | ConvertFrom-Json }} catch {{}}\n'
        f"if (-not $cfg -or -not $cfg.tun_enabled) {{ exit 0 }}\n"
        f"Start-Job -ScriptBlock {{\n"
        f"    $deadline = (Get-Date).AddSeconds(20)\n"
        f"    $idx = $null\n"
        f"    while ((Get-Date) -lt $deadline) {{\n"
        f"        $idx = (Get-NetAdapter -Name '{TUN_TASK_NAME}' -ErrorAction SilentlyContinue).ifIndex\n"
        f"        if ($idx) {{ break }}\n"
        f"        Start-Sleep -Milliseconds 500\n"
        f"    }}\n"
        f"    if ($idx) {{ route add 0.0.0.0 mask 0.0.0.0 0.0.0.0 if $idx metric 1 | Out-Null }}\n"
        f"}} | Out-Null\n"
        f'& "{exe}" run -c "{_tun_config_path()}" *> "{_tun_log_path()}"\n',
        encoding="utf-8",
    )
    return script


def register_tun_task() -> None:
    """One-time setup (needs an elevated caller — see module docstring
    above): (re)register the Scheduled Task that runs xray-core's TUN
    config as SYSTEM, with an at-startup trigger for autostart across
    reboots (the launch script itself, see _ensure_tun_script, checks
    vpn_settings.json's tun_enabled flag before actually doing anything,
    so this trigger firing doesn't mean capture silently comes back on
    when it was last turned off). `/run` still works on demand regardless
    of this trigger — that's how POST /vpn/tun/start uses it day to day.
    Idempotent (/f overwrites), safe to call again after a redeploy —
    registering never starts anything by itself."""
    script = _ensure_tun_script()
    tr = f'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{script}"'
    result = subprocess.run(
        ["schtasks", "/create", "/tn", TUN_TASK_NAME, "/tr", tr,
         "/sc", "onstart", "/delay", "0001:00",
         "/ru", "SYSTEM", "/rl", "highest", "/f"],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        raise VpnServiceError(
            "Не удалось зарегистрировать задачу планировщика для TUN-режима "
            f"(нужны права администратора для разового шага настройки): {result.stderr.strip()[:300]}"
        )


def _extract_outbound_server_ip(proxy_outbound: dict[str, Any]) -> str | None:
    """Best-effort: pull the proxy server's own address out of an xray
    outbound object (vless/vmess use "vnext", trojan/shadowsocks use
    "servers" — same shape otherwise), resolving a hostname to an IP if
    it isn't one already. Used to exclude the VPN server's own connection
    from the TUN's 0.0.0.0/0 capture — see build_tun_config's comment."""
    settings_obj = proxy_outbound.get("settings") or {}
    for entry in (settings_obj.get("vnext") or settings_obj.get("servers") or []):
        address = entry.get("address")
        if not address:
            continue
        try:
            ipaddress.ip_address(address)
            return address
        except ValueError:
            pass
        try:
            return socket.gethostbyname(address)
        except OSError:
            return None
    return None


def _physical_gateway() -> str | None:
    """The real default gateway's own IP for settings.vpn_tun_outbound_interface
    (the physical NIC) — queried fresh each time rather than cached, since
    the whole point is finding it independent of whatever 0.0.0.0/0 route
    the TUN adapter itself may currently hold."""
    script = (
        f"(Get-NetRoute -InterfaceAlias '{settings.vpn_tun_outbound_interface}' "
        "-DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Select-Object -First 1).NextHop"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=15,
    )
    gateway = result.stdout.strip()
    return gateway or None


def _set_uplink_exclusion_route(server_ip: str) -> None:
    """A host route (/32) to the VPN server itself via the real physical
    gateway — always wins over the TUN's later 0.0.0.0/0 route regardless
    of interface metric, since Windows picks the most specific prefix
    first. This is the fix Xray's own proxy/tun/README prescribes for
    "Xray-core itself try[ing] to reach its uplink through xray0 ...
    resulting infinite network loop" — without it, Xray's own connection
    to its proxy server gets recaptured by the very TUN adapter it just
    created, which is what an unbounded NetBIOS-broadcast storm in
    tun.log turned out to actually be (caught by hand in testing)."""
    gateway = _physical_gateway()
    if not gateway:
        raise VpnServiceError(
            f"Не удалось определить настоящий шлюз для интерфейса «{settings.vpn_tun_outbound_interface}» "
            "— без него сам VPN-сервер зациклится через TUN на себя."
        )
    subprocess.run(["route", "delete", server_ip], capture_output=True, timeout=10)
    result = subprocess.run(
        ["route", "add", server_ip, "mask", "255.255.255.255", gateway, "metric", "1"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise VpnServiceError(
            f"Не удалось добавить исключающий маршрут к {server_ip}: {result.stderr.strip()[:200]}"
        )


# Destinations that must never be captured by the TUN's default-route
# takeover, regardless of which processes are explicitly routed —
# production infrastructure this very box depends on. Discovered by hand:
# xtunnel's own long-lived tunnel connection went from a rock-steady ~2s
# per request (confirmed via its own diagnostics, not just external
# timing) down to 230ms the moment it stopped being captured — while
# short one-shot connections through the same TUN (a plain curl to
# google.com, or even a bare TLS probe straight to this same relay IP)
# were unaffected the whole time. Whatever the exact mechanism, it's
# specific to a sustained/multiplexed connection like xtunnel's, not TUN
# capture in general — so excluding it here beats trying to fully
# understand it. cname.xtunnel.ru is xtunnel's relay; may need updating
# if their infrastructure changes.
ALWAYS_DIRECT_HOSTS = ["cname.xtunnel.ru"]


def _resolve_host(host: str) -> str | None:
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    try:
        return socket.gethostbyname(host)
    except OSError:
        return None


def _set_static_exclusion_routes() -> None:
    gateway = _physical_gateway()
    if not gateway:
        return
    for host in ALWAYS_DIRECT_HOSTS:
        ip = _resolve_host(host)
        if not ip:
            continue
        subprocess.run(["route", "delete", ip], capture_output=True, timeout=10)
        subprocess.run(
            ["route", "add", ip, "mask", "255.255.255.255", gateway, "metric", "1"],
            capture_output=True, timeout=10,
        )


def _clear_uplink_exclusion_route_for_current_config() -> None:
    """Best-effort cleanup of whatever exclusion route the *previous*
    config-tun.json (still on disk at this point — the caller hasn't
    overwritten it yet) set up, before it's replaced. Silent no-op if
    there's nothing to clean, which is the common/expected case."""
    if not _tun_config_path().exists():
        return
    try:
        config = json.loads(_tun_config_path().read_text(encoding="utf-8"))
    except Exception:
        return
    for outbound in config.get("outbounds") or []:
        if outbound.get("tag") == "proxy":
            ip = _extract_outbound_server_ip(outbound)
            if ip:
                subprocess.run(["route", "delete", ip], capture_output=True, timeout=10)
            break


def _wait_for_tun_adapter(timeout: float = 15.0) -> int | None:
    """Poll for the TUN adapter to actually appear and return its
    ifIndex — `schtasks /run` is fire-and-forget, it doesn't wait for the
    process it launched (let alone for wintun to finish creating the
    adapter), so anything that needs the adapter to exist has to poll."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-NetAdapter -Name '{TUN_TASK_NAME}' -ErrorAction SilentlyContinue).ifIndex"],
            capture_output=True, text=True, timeout=10,
        )
        idx = result.stdout.strip()
        if idx.isdigit():
            return int(idx)
        time.sleep(0.5)
    return None


def start_tun(proxy_outbound: dict[str, Any], process_paths: list[str]) -> None:
    stop_tun()  # end any previous run + its exclusion route (reads the OLD config, still on disk here)
    _write_tun_config(proxy_outbound, process_paths)
    server_ip = _extract_outbound_server_ip(proxy_outbound)
    if server_ip:
        _set_uplink_exclusion_route(server_ip)
    _set_static_exclusion_routes()
    # Before /run — the launch script itself checks this flag (see
    # _ensure_tun_script) and no-ops if it's false, which is also what
    # makes the at-startup trigger safe: it has to already be true by the
    # time the task's own logic reads it, whether that's now or after the
    # next reboot.
    from app.data.vpn_settings_repository import get_vpn_settings_repository
    get_vpn_settings_repository().set_tun_enabled(True)
    result = subprocess.run(
        ["schtasks", "/run", "/tn", TUN_TASK_NAME], capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        raise VpnServiceError(
            "Не удалось запустить перехват на уровне ОС — если задача ещё не зарегистрирована, "
            f"нужен разовый шаг настройки от администратора: {result.stderr.strip()[:300]}"
        )
    # The script's own background job installs the default route (see
    # _ensure_tun_script) — this just waits for the adapter to confirm
    # xray actually started, for a fast/clear error here instead of the
    # caller finding out only from a later status check.
    if _wait_for_tun_adapter() is None:
        raise VpnServiceError(
            "Задача запущена, но TUN-адаптер не появился за 15 секунд — смотрите vpn/tun.log"
        )


def stop_tun() -> None:
    """The kill switch — ends the scheduled task's process tree, which
    tears down the TUN adapter (taking the default route the launch
    script's background job added for it down along with it — Windows
    drops routes scoped to an interface that disappears, and the
    adapter's ifIndex changes every run anyway so there's nothing stable
    left to `route delete` after the fact) and lets Windows fall back to
    the real network interface's own default route. Also flips
    tun_enabled off, so the at-startup trigger stays a no-op after the
    next reboot until explicitly turned on again. Safe to call even if
    nothing is running (schtasks just reports it wasn't)."""
    subprocess.run(["schtasks", "/end", "/tn", TUN_TASK_NAME], capture_output=True, timeout=15)
    _clear_uplink_exclusion_route_for_current_config()
    from app.data.vpn_settings_repository import get_vpn_settings_repository
    get_vpn_settings_repository().set_tun_enabled(False)


def tun_status() -> dict[str, Any]:
    # Deliberately NOT schtasks.exe's text table — this box's Windows is
    # Russian-localized, so its "Status" column comes back as "Выполняется"
    # (and mis-decoded on top of that under Python's default subprocess
    # text mode), so a plain "Running" in line check silently never
    # matched and the UI showed "off" for a task that was actually running
    # — caught by hand when it disagreed with a direct PowerShell check.
    # Get-ScheduledTask's .State is a CLR enum: its name ("Running",
    # "Ready", ...) doesn't get localized, so this is locale-proof.
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Get-ScheduledTask -TaskName '{TUN_TASK_NAME}' -ErrorAction SilentlyContinue).State.ToString()"],
        capture_output=True, text=True, timeout=15,
    )
    state = result.stdout.strip()
    if result.returncode != 0 or not state:
        return {"installed": False, "running": False, "log_tail": ""}
    running = state == "Running"
    log_tail = ""
    if _tun_log_path().exists():
        try:
            # PowerShell's `*>` redirect writes this file as UTF-16 (BOM),
            # not UTF-8 — reading it as UTF-8 "worked" (no decode error,
            # every other byte is ASCII) but produced a NUL between every
            # character, unreadable in the UI. "utf-16" auto-detects the
            # BOM's endianness rather than assuming LE.
            lines = _tun_log_path().read_text(encoding="utf-16", errors="replace").splitlines()
            log_tail = "\n".join(lines[-25:])
        except Exception:
            pass
    return {"installed": True, "running": running, "log_tail": log_tail}


def list_os_processes() -> list[dict[str, str]]:
    """Live snapshot of running processes with a resolvable exe path, for
    the "route this process" picker — always freshly queried, since what's
    running changes constantly and a stale list would let the admin "add"
    a process that already exited."""
    script = (
        "Get-Process | Where-Object { $_.Path } | "
        "Select-Object -Property Name, Path -Unique | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=15,
        )
    except Exception as exc:
        raise VpnServiceError(f"Не удалось получить список процессов: {exc}") from exc
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        data = json.loads(result.stdout)
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for item in data:
        path = item.get("Path")
        name = item.get("Name")
        if not path or path in seen:
            continue
        seen.add(path)
        out.append({"path": path, "label": name or Path(path).name})
    out.sort(key=lambda x: x["label"].lower())
    return out


# ── Wiring the split into ANY of our own pm2 processes ─────────────────
#
# Earlier this was two hardcoded env vars (TELEGRAM_PROXY, CLAUDE_PROXY)
# that only telegram_bot/api_server knew to read, each needing its own
# bit of application code — adding a third routable "function" meant a
# new settings.py field and a new call site. Generalized instead: httpx
# (and requests) trust HTTP_PROXY/HTTPS_PROXY/ALL_PROXY from the process's
# own environment by default (verified — neither python-telegram-bot's
# HTTPXRequest nor the Anthropic SDK's default client override
# trust_env), so setting those for *any* pm2 process and restarting it
# under them routes that process's outbound traffic through the proxy
# with zero code in the process itself. "Any process, not just the ones
# we hardcoded" becomes true for the whole fleet at once instead of one
# at a time.

PROXY_ENV_VARS = ("ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY")


def sync_process_proxy(pm2_name: str, heartbeat_name: str, label: str, mode: str, want: bool) -> None:
    """Set/clear HTTP(S)_PROXY+ALL_PROXY for one pm2 process and restart
    it under the new value — via app.api.system's existing detached
    restart-and-notify helper, so this composes with (not duplicates) the
    exact same "restart bot-app without killing the request that asked
    for it" handling already built there.
    """
    from app.data.vpn_settings_repository import get_vpn_settings_repository
    from app.api.system import _launch_restart_watcher

    socks = get_vpn_settings_repository().socks_proxy_url()
    value = socks if (want and socks) else ""
    extra_env = {name: value for name in PROXY_ENV_VARS}
    _launch_restart_watcher(pm2_name, heartbeat_name, label, mode, extra_env=extra_env)
