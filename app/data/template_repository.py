from pathlib import Path
import json
from typing import List, Dict, Any

class TemplateRepository:
    def __init__(self, path: str | Path = "message_templates.json") -> None:
        self._file = Path(path)
        self._data: List[Dict[str, Any]] = self._load()
        self._counter = max((int(t.get("id", 0)) for t in self._data if str(t.get("id", "")).isdigit()), default=0)

    def _load(self) -> List[Dict[str, Any]]:
        if self._file.exists():
            try:
                return json.loads(self._file.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save(self) -> None:
        self._file.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _generate_id(self) -> str:
        self._counter += 1
        return str(self._counter)

    def list(self) -> List[Dict[str, Any]]:
        return list(self._data)

    def create(self, name: str, text: str) -> Dict[str, Any]:
        record = {"id": self._generate_id(), "name": name, "text": text}
        self._data.append(record)
        self._save()
        return record

    def delete(self, tpl_id: str) -> None:
        self._data = [t for t in self._data if str(t.get("id")) != str(tpl_id)]
        self._save()
