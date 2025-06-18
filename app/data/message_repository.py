import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


class MessageRepository:
    def __init__(self, path: str | Path = "messages.json") -> None:
        self._file = Path(path)
        self._data: List[Dict[str, Any]] = self._load()
        self._counter = max(
            (int(
                m.get(
                    "id",
                    0)) for m in self._data if str(
                m.get(
                    "id",
                    "")).isdigit()),
            default=0)

    def _load(self) -> List[Dict[str, Any]]:
        if self._file.exists():
            try:
                return json.loads(self._file.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save(self) -> None:
        self._file.write_text(
            json.dumps(
                self._data,
                ensure_ascii=False,
                indent=2),
            encoding="utf-8")

    def _generate_id(self) -> str:
        self._counter += 1
        return str(self._counter)

    def list(self) -> List[Dict[str, Any]]:
        return sorted(
            self._data,
            key=lambda x: x.get(
                "timestamp",
                ""),
            reverse=True)

    def create(self, record: Dict[str, Any]) -> Dict[str, Any]:
        if "id" not in record:
            record["id"] = self._generate_id()
        self._data.append(record)
        self._save()
        return record

    def accept(self, msg_id: str) -> Optional[Dict[str, Any]]:
        for m in self._data:
            if str(m.get("id")) == str(msg_id):
                m["status"] = "Принято"
                m["accepted"] = True
                m["timestamp_accept"] = datetime.utcnow().isoformat()
                self._save()
                return m
        return None

    def accept_by_details(self, user_id: str,
                          message_id: int) -> Optional[Dict[str, Any]]:
        for m in self._data:
            if str(m.get("user_id")) == str(
                    user_id) and m.get("message_id") == message_id:
                m["status"] = "Принято"
                m["accepted"] = True
                m["timestamp_accept"] = datetime.utcnow().isoformat()
                self._save()
                return m
        return None
