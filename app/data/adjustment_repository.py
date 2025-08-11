import json
import os
from typing import List, Dict, Any, Optional

from app.config import ADJUSTMENTS_FILE
from app.utils.logger import log


class AdjustmentRepository:
    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or ADJUSTMENTS_FILE
        self._data: List[Dict[str, Any]] = self._load()
        if not self._data:
            log("⚠️ AdjustmentRepository loaded no adjustments")
        self._counter = max(
            (int(
                item.get(
                    "id",
                    0)) for item in self._data if str(
                item.get("id")).isdigit()),
            default=0)

    def _load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self._file):
            example = self._file.replace('.json', '.example.json')
            if os.path.exists(example):
                try:
                    with open(example, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    with open(self._file, 'w', encoding='utf-8') as out:
                        json.dump(data, out, ensure_ascii=False, indent=2)
                    return data
                except Exception:
                    return []
            return []
        try:
            with open(self._file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = []
        if not data:
            example = self._file.replace('.json', '.example.json')
            if os.path.exists(example):
                try:
                    with open(example, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    with open(self._file, 'w', encoding='utf-8') as out:
                        json.dump(data, out, ensure_ascii=False, indent=2)
                except Exception:
                    data = []
        return data

    def _save(self) -> None:
        with open(self._file, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _generate_id(self) -> int:
        self._counter += 1
        return self._counter

    def list(self) -> List[Dict[str, Any]]:
        return list(self._data)

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if 'id' not in data or any(str(it.get('id')) == str(
                data['id']) for it in self._data):
            data['id'] = self._generate_id()
        self._data.append(data)
        self._save()
        return data

    def update(self, adj_id: str,
               updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for item in self._data:
            if str(item.get('id')) == str(adj_id):
                item.update(
                    {k: v for k, v in updates.items() if v is not None})
                self._save()
                return item
        return None

    def delete(self, adj_id: str) -> None:
        self._data = [
            it for it in self._data if str(
                it.get('id')) != str(adj_id)]
        self._save()
