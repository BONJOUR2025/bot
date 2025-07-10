import json
import os
from datetime import date, timedelta
from typing import List, Dict, Any, Optional

from app.config import VACATIONS_FILE
from app.utils.logger import log


class VacationRepository:
    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or VACATIONS_FILE
        log(f"📂 Loading vacations from {self._file}")
        self._data: List[Dict[str, Any]] = self._load()
        log(f"✅ Loaded vacations: {len(self._data)}")
        if not self._data:
            log("⚠️ VacationRepository loaded no vacations")
        self._counter = max(
            (int(
                v.get(
                    "id",
                    0)) for v in self._data if str(
                v.get("id")).isdigit()),
            default=0)

    def _load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self._file):
            example = self._file.replace('.json', '.example.json')
            if os.path.exists(example):
                log(f"⚠️ {self._file} not found. Using example {example}")
                try:
                    with open(example, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    with open(self._file, "w", encoding="utf-8") as out:
                        json.dump(data, out, ensure_ascii=False, indent=2)
                    return data
                except Exception as e:
                    log(f"❌ Failed reading example {example}: {e}")
                    return []
            log(f"❌ {self._file} not found and no example")
            return []
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            log(f"❌ Failed reading {self._file}: {e}")
            data = []
        if not data:
            example = self._file.replace('.json', '.example.json')
            if os.path.exists(example):
                try:
                    log(f"⚠️ Using example {example}")
                    with open(example, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    with open(self._file, "w", encoding="utf-8") as out:
                        json.dump(data, out, ensure_ascii=False, indent=2)
                except Exception as e:
                    log(f"❌ Failed reading example {example}: {e}")
                    data = []
        return data

    def _save(self) -> None:
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _generate_id(self) -> int:
        self._counter += 1
        return self._counter

    def list(
        self,
        employee_id: Optional[str] = None,
        vac_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        result = []
        for item in self._data:
            if employee_id and str(item.get("employee_id")) != str(employee_id):
                continue
            if vac_type and item.get("type") != vac_type:
                continue
            if date_from and str(item.get("start_date")) < date_from:
                continue
            if date_to and str(item.get("end_date")) > date_to:
                continue
            result.append(item)
        result.sort(key=lambda v: v.get("start_date", ""))
        return result

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if "id" not in data or any(
                str(v.get("id")) == str(data["id"]) for v in self._data):
            data["id"] = self._generate_id()
        self._data.append(data)
        self._save()
        return data

    def update(self, vac_id: str,
               updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for item in self._data:
            if str(item.get("id")) == str(vac_id):
                item.update(
                    {k: v for k, v in updates.items() if v is not None})
                self._save()
                return item
        return None

    def delete(self, vac_id: str) -> None:
        self._data = [v for v in self._data if str(v.get("id")) != str(vac_id)]
        self._save()

    def list_active(self) -> List[Dict[str, Any]]:
        today = date.today().isoformat()
        active = [
            v
            for v in self._data
            if str(v.get("start_date")) <= today <= str(v.get("end_date"))
        ]
        active.sort(key=lambda v: v.get("start_date", ""))
        return active

    def list_tomorrow(self) -> List[Dict[str, Any]]:
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        reminder = [v for v in self._data if str(v.get("start_date")) == tomorrow]
        reminder.sort(key=lambda v: v.get("start_date", ""))
        return reminder
