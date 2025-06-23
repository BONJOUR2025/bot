from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonStorage:
    """Simple JSON file storage."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if self.path.exists():
            with self.path.open('r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save(self, data: dict[str, Any]) -> None:
        with self.path.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
