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
        type: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Payout]:
        data = self._load()
        result: List[Payout] = []
        from_dt = datetime.fromisoformat(from_date) if from_date else None
        to_dt = datetime.fromisoformat(to_date) if to_date else None
        for item in data:
            if employee_id and str(item.get("user_id")) != str(employee_id):
                continue
            if type and item.get("type") != type:
                continue
            if status and item.get("status") != status:
                continue
            created_str = item.get("created_at")
            if created_str:
                try:
                    created = datetime.fromisoformat(created_str)
                except Exception:
                    created = None
            else:
                created = None
            if from_dt and created and created < from_dt:
                continue
            if to_dt and created and created > to_dt:
                continue
            result.append(Payout(**item))
        return result

    async def create_payout(self, data: PayoutCreate) -> Payout:
        items = self._load()
        payout = Payout(
            id=str(len(items) + 1),
            user_id=data.user_id,
            name=data.name,
            amount=data.amount,
            type=data.type,
            method=data.method,
            status="pending",
            created_at=datetime.utcnow().isoformat(),
            comment=data.comment,
        )
        items.append(payout.model_dump())
        self._save(items)
        return payout

    async def update_payout(self, payout_id: str, update: PayoutUpdate) -> Optional[Payout]:
        items = self._load()
        for item in items:
            if str(item.get("id")) == str(payout_id):
                if update.status is not None:
                    item["status"] = update.status
                if update.comment is not None:
                    item["comment"] = update.comment
                self._save(items)
                return Payout(**item)
        return None

