import json
import os
from typing import List, Dict, Any, Optional

from app.config import BONUSES_PENALTIES_FILE

DEFAULT_INCENTIVES_FILE = "bonuses_penalties.json"
from app.utils.logger import log


class IncentiveRepository:
    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or BONUSES_PENALTIES_FILE or DEFAULT_INCENTIVES_FILE
        log(f"📂 Loading incentives from {self._file}")
        self._data: List[Dict[str, Any]] = self._load()
        log(f"✅ Loaded incentives: {len(self._data)}")
        self._counter = max(
            (int(item.get("id", 0)) for item in self._data if str(item.get("id")).isdigit()),
            default=0,
        )

    def _load(self) -> List[Dict[str, Any]]:
        if not self._file or not os.path.exists(self._file):
            example = (
                self._file.replace('.json', '.example.json') if self._file else 'bonuses_penalties.example.json'
            )
            if os.path.exists(example):
                log(f"⚠️ {self._file} not found. Using example {example}")
                try:
                    with open(example, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    with open(self._file, 'w', encoding='utf-8') as out:
                        json.dump(data, out, ensure_ascii=False, indent=2)
                    return data
                except Exception as e:
                    log(f"❌ Failed reading example {example}: {e}")
                    return []
            log(f"❌ {self._file} not found and no example")
            return []
        try:
            with open(self._file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            log(f"❌ Failed reading {self._file}: {e}")
            data = []
        if not data:
            example = (
                self._file.replace('.json', '.example.json') if self._file else 'bonuses_penalties.example.json'
            )
            if os.path.exists(example):
                try:
                    log(f"⚠️ Using example {example}")
                    with open(example, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    with open(self._file, 'w', encoding='utf-8') as out:
                        json.dump(data, out, ensure_ascii=False, indent=2)
                except Exception as e:
                    log(f"❌ Failed reading example {example}: {e}")
                    data = []
        return data

    def _save(self) -> None:
        with open(self._file, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _generate_id(self) -> int:
        self._counter += 1
        return self._counter

    def list(
        self,
        employee_id: Optional[str] = None,
        typ: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        result = []
        for item in self._data:
            if employee_id and str(item.get("employee_id")) != str(employee_id):
                continue
            if typ and item.get("type") != typ:
                continue
            if date_from and str(item.get("date")) < date_from:
                continue
            if date_to and str(item.get("date")) > date_to:
                continue
            result.append(item)
        result.sort(key=lambda x: x.get("date", ""), reverse=True)
        return result

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if 'id' not in data or any(str(it.get('id')) == str(data['id']) for it in self._data):
            data['id'] = self._generate_id()
        self._data.append(data)
        self._save()
        return data

    def update(self, item_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for item in self._data:
            if str(item.get('id')) == str(item_id):
                if item.get('locked'):
                    return None
                item.update({k: v for k, v in updates.items() if v is not None})
                self._save()
                return item
        return None

    def delete(self, item_id: str) -> bool:
        for item in self._data:
            if str(item.get('id')) == str(item_id):
                if item.get('locked'):
                    return False
                self._data.remove(item)
                self._save()
                return True
        return False
