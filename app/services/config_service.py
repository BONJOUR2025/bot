from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class ConfigService:
    """Load and save settings stored in config.json."""

    def __init__(self, path: str | Path = "config.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load_raw(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return {}
        if isinstance(data, dict):
            return data
        return {}

    @staticmethod
    def _normalize_for_response(data: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(key, str):
                normalized[key.lower()] = value
            else:
                normalized[key] = value
        return normalized

    @staticmethod
    def _prepare_for_storage(data: Dict[str, Any]) -> Dict[str, Any]:
        prepared: Dict[str, Any] = {}
        for key, value in data.items():
            if not isinstance(key, str):
                continue
            prepared[key.upper()] = value
        return prepared

    def load(self) -> Dict[str, Any]:
        raw = self._load_raw()
        return self._normalize_for_response(raw)

    def save(self, data: Dict[str, Any], *, already_prepared: bool = False) -> Dict[str, Any]:
        payload = data if already_prepared else self._prepare_for_storage(data)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return self._normalize_for_response(payload)

    def patch(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        current = self._load_raw()
        current.update(self._prepare_for_storage(updates))
        return self.save(current, already_prepared=True)

    async def upload(self, file_bytes: bytes) -> None:
        try:
            data = json.loads(file_bytes.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Invalid JSON: {exc}")
        prepared = data if isinstance(data, dict) else {}
        self.save(self._prepare_for_storage(prepared), already_prepared=True)
