from datetime import datetime
from typing import List, Optional, Dict, Any

from app.schemas.payout import Payout, PayoutCreate, PayoutUpdate
from app.data.payout_repository import PayoutRepository
from .telegram_service import TelegramService

import logging
from pathlib import Path

logger = logging.getLogger("payout_actions")
if not logger.handlers:
    Path("logs").mkdir(exist_ok=True)
    handler = logging.FileHandler("logs/payout_actions.log", encoding="utf-8")
    formatter = logging.Formatter("[%(asctime)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class PayoutService:
    def __init__(
        self,
        repo: Optional[PayoutRepository] = None,
        telegram_service: Optional["TelegramService"] = None,
    ) -> None:
        self._repo = repo or PayoutRepository()
        self._telegram = telegram_service

    async def list_payouts(
        self,
        employee_id: Optional[str] = None,
        payout_type: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Payout]:
        rows = self._repo.list(
            employee_id,
            payout_type,
            status,
            from_date,
            to_date)
        return [Payout(**r) for r in rows]

    async def create_payout(self, data: PayoutCreate) -> Payout:
        payout_dict: Dict = {
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
        created = self._repo.create(payout_dict)
        logger.info(
            f"🆕 Выплата '{
                created['payout_type']}' на {
                created['amount']} ₽ для user_id {
                created['user_id']} — статус: {
                    created['status']}")
        if self._telegram and data.sync_to_bot:
            try:
                await self._telegram.send_payout_request_to_admin(created)
            except Exception as exc:
                logger.warning(f"Не удалось отправить в бот: {exc}")
        return Payout(**created)

    async def update_payout(
            self,
            payout_id: str,
            update: PayoutUpdate) -> Optional[Payout]:
        updated = self._repo.update(
            payout_id, update.model_dump(
                exclude_none=True))
        if updated:
            logger.info(
                f"✏️ Выплата {payout_id} обновлена — статус: {
                    updated.get('status')}")
            return Payout(**updated)
        return None

    async def delete_payouts(self, ids: List[str]) -> None:
        if not ids:
            return
        self._repo.delete_many(ids)
        logger.info(f"🗑 Удалены выплаты: {', '.join(ids)}")

    async def delete_payout(self, payout_id: str) -> bool:
        deleted = self._repo.delete(payout_id)
        if deleted:
            logger.info(f"🗑 Удалена выплата {payout_id}")
        return deleted

    async def list_active_payouts(self) -> List[Payout]:
        """Return payouts that are pending approval or already approved."""
        rows = self._repo.load_all()
        active = [
            r for r in rows if r.get("status") in (
                "В ожидании",
                "Разрешено",
                "Ожидает",
                "pending")]
        return [Payout(**r) for r in active]
