import json
import os
from datetime import datetime
from typing import List, Optional

from ..config import ADVANCE_REQUESTS_FILE
from ..schemas.payout import Payout, PayoutCreate, PayoutUpdate


class PayoutService:
    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or ADVANCE_REQUESTS_FILE

    def _load(self) -> List[dict]:
        if not os.path.exists(self._file):
            return []
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self, data: List[dict]) -> None:
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    async def list_payouts(
        self,
        employee_id: Optional[str] = None,
        payout_type: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Payout]:
        data = self._load()
        result: List[Payout] = []
        from_dt = datetime.fromisoformat(from_date) if from_date else None
        to_dt = datetime.fromisoformat(to_date) if to_date else None
        for idx, item in enumerate(data):
            if employee_id and str(item.get("user_id")) != str(employee_id):
                continue
            if payout_type and item.get("payout_type") != payout_type:
                continue
            if status and item.get("status") != status:
                continue
            ts_str = item.get("timestamp")
            created = None
            if ts_str:
                try:
                    created = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass
            if from_dt and created and created < from_dt:
                continue
            if to_dt and created and created > to_dt:
                continue
            result.append(Payout(idx=idx, **item))
        return result

    async def create_payout(self, data: PayoutCreate) -> Payout:
        items = self._load()
        payout_dict = {
            "user_id": data.user_id,
            "name": data.name,
            "phone": data.phone,
            "bank": data.bank,
            "amount": data.amount,
            "method": data.method,
            "payout_type": data.payout_type,
            "status": "В ожидании",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        items.append(payout_dict)
        self._save(items)
        return Payout(idx=len(items) - 1, **payout_dict)

    async def update_payout(self, idx: int, update: PayoutUpdate) -> Optional[Payout]:
        items = self._load()
        if 0 <= idx < len(items):
            item = items[idx]
            for field, value in update.model_dump(exclude_none=True).items():
                item[field] = value
            self._save(items)
            return Payout(idx=idx, **item)
        return None

    async def delete_payouts(self, indices: List[int]) -> None:
        items = self._load()
        for idx in sorted(set(indices), reverse=True):
            if 0 <= idx < len(items):
                items.pop(idx)
        self._save(items)

