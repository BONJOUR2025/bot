from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.utils.logger import log


class JsonStorage:
    """Simple JSON file storage."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        """Load data from the JSON file, falling back to an example copy."""
        log(f"📂 Loading data from: {self.path}")
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                log(f"❌ Failed reading {self.path}: {e}")
                data = None
            if not data:
                example = self.path.with_suffix(".example.json")
                if example.exists():
                    log(f"⚠️ Using example file {example}")
                    with example.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.save(data)
            log(f"✅ Records loaded: {len(data or {})}")
            return data or {}

        example = self.path.with_suffix('.example.json')
        if example.exists():
            log(f"⚠️ {self.path} not found. Loading example {example}")
            with example.open('r', encoding='utf-8') as f:
                data = json.load(f)
            # seed real file so future writes persist
            with self.path.open('w', encoding='utf-8') as fw:
                json.dump(data, fw, ensure_ascii=False, indent=2)
            log(f"✅ Records loaded: {len(data)}")
            return data
        log(f"❌ {self.path} missing and no example file")
        return {}

    def save(self, data: dict[str, Any]) -> None:
        with self.path.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
