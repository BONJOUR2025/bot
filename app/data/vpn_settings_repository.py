"""Repository for split-tunnel VPN configuration — which of our own outbound
connections (Telegram, Claude API, ...) go through the local xray-core proxy
vs direct, plus the subscription URL and which of its servers is active.

Same JSON-file-backed pattern as payroll_comments_repository.py /
apprentice_attendance_repository.py: one small mutable document, not
per-record rows, so a plain read-modify-write is simpler and safer than a
DB table here.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.settings import settings

DEFAULT_FILE = "vpn_settings.json"

# Function keys the split-tunnel UI can toggle. Every service that wants to
# honor the split must ask should_route(key) for its own key — adding a row
# to this dict is what makes a new toggle show up in Settings, but a service
# still has to actually read it (see app/core/application.py and
# app/services/llm_client.py for the two wired up today).
ROUTABLE_FUNCTIONS: dict[str, str] = {
    "telegram": "Telegram-бот (long polling)",
    "claude": "Claude API (интервью, проверки текста)",
}

_DEFAULT_DOC: dict[str, Any] = {
    "subscription_url": "",
    "active_profile": None,  # {"remarks": str, "socks_proxy": str, "http_proxy": str}
    "route": {k: False for k in ROUTABLE_FUNCTIONS},
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
        merged["route"] = {**_DEFAULT_DOC["route"], **(doc.get("route") or {})}
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

    def set_active_profile(self, remarks: str, socks_proxy: str, http_proxy: str) -> dict[str, Any]:
        self._data["active_profile"] = {
            "remarks": remarks, "socks_proxy": socks_proxy, "http_proxy": http_proxy,
        }
        self._save()
        return self.get()

    def set_route(self, flags: dict[str, bool]) -> dict[str, Any]:
        for key, value in flags.items():
            if key in ROUTABLE_FUNCTIONS:
                self._data["route"][key] = bool(value)
        self._save()
        return self.get()

    def should_route(self, function_key: str) -> bool:
        """Whether `function_key` should go through the VPN proxy right now —
        both the toggle AND an actually-configured server, since a toggle
        left on with no server selected must fail safe to "direct", not to
        pointing every affected client at a proxy port nothing is listening
        on."""
        if not self._data.get("active_profile"):
            return False
        return bool(self._data.get("route", {}).get(function_key, False))

    def socks_proxy_url(self) -> str | None:
        profile = self._data.get("active_profile")
        return profile.get("socks_proxy") if profile else None


_repo: VpnSettingsRepository | None = None


def get_vpn_settings_repository() -> VpnSettingsRepository:
    global _repo
    if _repo is None:
        _repo = VpnSettingsRepository()
    return _repo
