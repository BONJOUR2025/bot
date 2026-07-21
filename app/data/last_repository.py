import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

DEFAULT_FILE = "lasts.json"


class LastRepository:
    """Library of shoe-last (колодка) 3D scans: manual metadata (article,
    size, model, material) plus measurements extracted once at upload time
    via scm_parser_service, so matching against a foot scan later doesn't
    need to re-parse the last's file."""

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or DEFAULT_FILE
        self._data: List[Dict[str, Any]] = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self._file):
            return []
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self) -> None:
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def list(self) -> List[Dict[str, Any]]:
        return list(self._data)

    def get(self, last_id: str) -> Optional[Dict[str, Any]]:
        for item in self._data:
            if item.get("id") == last_id:
                return item
        return None

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex,
            "article": data.get("article", ""),
            "size": data.get("size", ""),
            "model": data.get("model", ""),
            "material": data.get("material", ""),
            "note": data.get("note", ""),
            "scan_file_url": data.get("scan_file_url", ""),
            "blocks": data["blocks"],  # list of {side, point_count, length_mm, width_mm, height_mm, ball_girth_mm}
            "created_at": datetime.now().isoformat(),
        }
        self._data.append(record)
        self._save()
        return record

    def set_scan_file_url(self, last_id: str, url: str) -> None:
        for item in self._data:
            if item.get("id") == last_id:
                item["scan_file_url"] = url
                self._save()
                return

    def delete(self, last_id: str) -> Optional[Dict[str, Any]]:
        for i, item in enumerate(self._data):
            if item.get("id") == last_id:
                removed = self._data.pop(i)
                self._save()
                return removed
        return None
