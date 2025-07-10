import json
from pathlib import Path
from typing import Any, Dict


class ConfigService:
    """Load and save settings stored in config.json."""

    def __init__(self, path: str | Path = "config.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data

    def patch(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        current = self.load()
        current.update(updates)
        return self.save(current)

    async def upload(self, file_bytes: bytes) -> None:
        try:
            data = json.loads(file_bytes.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Invalid JSON: {exc}")
        self.save(data)
