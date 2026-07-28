import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

DEFAULT_FILE = "last_articles.json"


class LastArticleRepository:
    """Registry of shoe-last model/article numbers (колодка №4977, ...),
    separate from the individual size x fullness scans in LastRepository.

    Exists so the "add a last" form can offer a dropdown of known article
    numbers instead of free text -- a typo in a hand-typed article number
    (4977 vs 4977 with a trailing space) silently splits one model family
    into two groups in the library grid. `code` is the identifier lasts are
    grouped and matched by; `name`/`note` are just a human label."""

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

    def get(self, article_id: str) -> Optional[Dict[str, Any]]:
        for item in self._data:
            if item.get("id") == article_id:
                return item
        return None

    def get_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        code = (code or "").strip()
        for item in self._data:
            if item.get("code") == code:
                return item
        return None

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex,
            "code": (data.get("code") or "").strip(),
            "name": data.get("name", ""),
            "note": data.get("note", ""),
            "created_at": datetime.now().isoformat(),
        }
        self._data.append(record)
        self._save()
        return record

    def update(self, article_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for item in self._data:
            if item.get("id") == article_id:
                if "code" in data:
                    item["code"] = (data["code"] or "").strip()
                if "name" in data:
                    item["name"] = data["name"]
                if "note" in data:
                    item["note"] = data["note"]
                self._save()
                return item
        return None

    def delete(self, article_id: str) -> Optional[Dict[str, Any]]:
        for i, item in enumerate(self._data):
            if item.get("id") == article_id:
                removed = self._data.pop(i)
                self._save()
                return removed
        return None
