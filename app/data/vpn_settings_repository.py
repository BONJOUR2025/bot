"""Repository for split-tunnel VPN configuration — which of our own pm2
processes go through the local xray-core proxy vs direct, plus the
subscription URL and which of its servers is active.

Same JSON-file-backed pattern as payroll_comments_repository.py /
apprentice_attendance_repository.py: one small mutable document, not
per-record rows, so a plain read-modify-write is simpler and safer than a
DB table here.

`route` used to be keyed by a fixed, hand-picked set of "functions"
(telegram/claude) that each needed its own bit of wiring in the service
that used it. That meant every new thing anyone wanted to route through
the VPN was a code change. It's now keyed by pm2 process name instead —
any process app/api/system.py's fleet registry knows about is routable,
with no code change here: see app/services/vpn_service.py.sync_process_proxy,
which flips a process's HTTP(S)_PROXY/ALL_PROXY and restarts it via
`pm2 restart --update-env`, working for anything the process's own HTTP
client trusts the environment for (httpx and requests do by default).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.settings import settings

DEFAULT_FILE = "vpn_settings.json"

_DEFAULT_DOC: dict[str, Any] = {
    "subscription_url": "",
    "active_profile": None,  # {"remarks", "socks_proxy", "http_proxy", "outbound"} — "outbound" is
    # the raw xray-core outbound object for the selected server, kept around so the TUN config (below)
    # can be rebuilt without re-fetching the subscription every time a process is added/removed.
    "route": {},  # {pm2_process_key: bool} — arbitrary keys, not a fixed set
    # Arbitrary OS processes (browser, third-party apps — not just our own pm2
    # fleet) routed through xray-core's TUN inbound by process path. See
    # vpn_service's TUN section: [{"path": str, "label": str}].
    "tun_processes": [],
    # Random per-install id sent as X-Hwid when fetching a subscription —
    # some providers gate the real server list behind a device-registration
    # check keyed on this (see vpn_service.SUBSCRIPTION_HEADERS). Generated
    # once on first use, not user-facing.
    "device_hwid": None,
    "updated_at": None,
}


class VpnSettingsRepository:
    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file = Path(file_path or getattr(settings, "vpn_settings_file", DEFAULT_FILE))
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self._file.exists():
            return dict(_DEFAULT_DOC)
        try:
            with open(self._file, encoding="utf-8") as f:
                doc = json.load(f)
        except Exception:
            return dict(_DEFAULT_DOC)
        merged = dict(_DEFAULT_DOC)
        merged.update(doc)
        merged["route"] = dict(doc.get("route") or {})
        merged["tun_processes"] = list(doc.get("tun_processes") or [])
        return merged

    def _save(self) -> None:
        self._data["updated_at"] = datetime.now().isoformat()
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self) -> dict[str, Any]:
        return dict(self._data)

    def set_subscription_url(self, url: str) -> dict[str, Any]:
        self._data["subscription_url"] = url.strip()
        self._save()
        return self.get()

    def set_device_hwid(self, hwid: str) -> dict[str, Any]:
        self._data["device_hwid"] = hwid
        self._save()
        return self.get()

    def set_active_profile(
        self, remarks: str, socks_proxy: str, http_proxy: str | None, outbound: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._data["active_profile"] = {
            "remarks": remarks, "socks_proxy": socks_proxy, "http_proxy": http_proxy, "outbound": outbound,
        }
        self._save()
        return self.get()

    def active_outbound(self) -> dict[str, Any] | None:
        profile = self._data.get("active_profile")
        return (profile or {}).get("outbound")

    def set_tun_processes(self, processes: list[dict[str, str]]) -> dict[str, Any]:
        self._data["tun_processes"] = processes
        self._save()
        return self.get()

    def set_route(self, flags: dict[str, bool]) -> dict[str, Any]:
        """No key restriction here — app/api/vpn.py validates each key
        against the live pm2 fleet before calling this, so an invalid key
        never reaches this repository, but the repository itself doesn't
        need to know that universe to stay correct."""
        for key, value in flags.items():
            self._data["route"][key] = bool(value)
        self._save()
        return self.get()

    def should_route(self, process_key: str) -> bool:
        """Whether `process_key` should go through the VPN proxy right now —
        both the toggle AND an actually-configured server, since a toggle
        left on with no server selected must fail safe to "direct", not to
        pointing every affected client at a proxy port nothing is listening
        on."""
        if not self._data.get("active_profile"):
            return False
        return bool(self._data.get("route", {}).get(process_key, False))

    def socks_proxy_url(self) -> str | None:
        profile = self._data.get("active_profile")
        return profile.get("socks_proxy") if profile else None


_repo: VpnSettingsRepository | None = None


def get_vpn_settings_repository() -> VpnSettingsRepository:
    global _repo
    if _repo is None:
        _repo = VpnSettingsRepository()
    return _repo
