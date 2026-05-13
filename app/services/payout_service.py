from datetime import datetime
from typing import List, Optional, Dict, Any

from app.schemas.payout import Payout, PayoutCreate, PayoutUpdate
from app.data.payout_repository import PayoutRepository
from .telegram_service import TelegramService
from app.core.enums import PAYOUT_STATUSES

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
        push_service=None,
    ) -> None:
        self._repo = repo or PayoutRepository()
        self._telegram = telegram_service
        self._push = push_service

    @staticmethod
    def _serialize_timestamp(value: datetime | str) -> str:
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(value, str):
            cleaned = value.strip()
            try:
                parsed = datetime.fromisoformat(cleaned)
            except ValueError:
                try:
                    parsed = datetime.fromisoformat(cleaned.replace(" ", "T"))
                except ValueError:
                    return cleaned
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        raise TypeError("Unsupported timestamp type")

    async def list_payouts(
        self,
        employee_id: Optional[str] = None,
        payout_type: Optional[str] = None,
        status: Optional[str] = None,
        method: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Payout]:
        self._repo.reload()
        rows = self._repo.list(
            employee_id,
            payout_type,
            status,
            method,
            from_date,
            to_date)
        return [Payout(**r) for r in rows]

    @staticmethod
    def _fuzzy_find_cash_move(payout_dict: Dict) -> Optional[str]:
        """Find a Firebird cash movement matching payout by amount and date ±1 day."""
        from datetime import timedelta, date as date_cls
        try:
            from app.services.firebird_service import get_firebird_service
            ts = str(payout_dict.get("timestamp") or "")[:10]
            if not ts:
                return None
            payout_date = date_cls.fromisoformat(ts)
            payout_amount = float(payout_dict.get("amount") or 0)
            moves = get_firebird_service().get_cash_moves(
                date_from=payout_date - timedelta(days=1),
                date_to=payout_date + timedelta(days=1),
            )
            for m in moves:
                move_date_str = str(m.get("DK_DATE") or "")[:10]
                try:
                    move_date = date_cls.fromisoformat(move_date_str)
                except ValueError:
                    continue
                if (abs((payout_date - move_date).days) <= 1
                        and abs(payout_amount - float(m.get("SUMM") or 0)) < 0.01):
                    return str(m.get("ID_KASSES_MOVE") or "")
        except Exception as exc:
            logger.warning(f"Cash move fuzzy match failed: {exc}")
        return None

    async def find_cash_move_for_payout(self, payout_id: int) -> Optional[str]:
        """Manually find and persist a cash movement link for an existing payout."""
        self._repo.reload()
        payout = next((p for p in self._repo.load_all() if p["id"] == payout_id), None)
        if not payout:
            return None
        move_id = self._fuzzy_find_cash_move(payout)
        if move_id:
            self._repo.update(str(payout_id), {"cash_move_id": move_id})
            logger.info(f"🔗 Выплата {payout_id} привязана к движению {move_id}")
        return move_id

    async def find_cash_moves_bulk(self, ids: List[int]) -> Dict[int, Optional[str]]:
        """Find and persist cash movement links for multiple payouts."""
        results: Dict[int, Optional[str]] = {}
        for payout_id in ids:
            results[payout_id] = await self.find_cash_move_for_payout(payout_id)
        return results

    async def create_payout(self, data: PayoutCreate) -> Payout:
        self._repo.reload()
        payout_dict: Dict = {
            "user_id": data.user_id,
            "name": data.name,
            "phone": data.phone,
            "card_number": data.card_number or "",
            "bank": data.bank,
            "amount": data.amount,
            "method": data.method,
            "payout_type": data.payout_type,
            "status": "Выплачено" if data.cash_move_id else PAYOUT_STATUSES[0],
            "note": data.note or "",
            "show_note_in_bot": data.show_note_in_bot,
            "force_notify_cashier": data.force_notify_cashier,
            "cash_move_id": data.cash_move_id or None,
        }
        timestamp_value = data.timestamp or datetime.now()
        payout_dict["timestamp"] = self._serialize_timestamp(timestamp_value)

        # Auto-link to cash movement for "Из кассы" payouts
        if not payout_dict["cash_move_id"] and "кассы" in (data.method or "").lower():
            move_id = self._fuzzy_find_cash_move(payout_dict)
            if move_id:
                payout_dict["cash_move_id"] = move_id
                payout_dict["status"] = "Выплачено"

        created = self._repo.create(payout_dict)
        logger.info(
            f"🆕 Выплата '{created['payout_type']}' на {created['amount']} ₽ для user_id {created['user_id']} — статус: {created['status']}"
        )
        if self._telegram and data.sync_to_bot:
            try:
                await self._telegram.send_payout_request_to_admin(created)
            except Exception as exc:
                logger.warning(f"Не удалось отправить в бот: {exc}")
        return Payout(**created)

    async def update_payout(
        self,
        payout_id: str,
        update: PayoutUpdate,
    ) -> Optional[Payout]:
        self._repo.reload()
        updates = update.model_dump(exclude_none=True)
        notify = updates.pop("notify_user", True)
        if "timestamp" in updates:
            updates["timestamp"] = self._serialize_timestamp(updates["timestamp"])
        if not updates:
            return None
        updated = self._repo.update(payout_id, updates)
        if not updated:
            return None
        if "status" in updates:
            # notify user if status has changed
            if self._telegram and notify:
                try:
                    status_messages = {
                        PAYOUT_STATUSES[1]: "✅ Ваша заявка одобрена",
                        PAYOUT_STATUSES[2]: "❌ Ваша заявка отклонена",
                        PAYOUT_STATUSES[3]: "📤 Выплата отправлена",
                    }
                    message = status_messages.get(updates["status"])
                    if message:
                        await self._telegram.send_message_to_user(
                            updated["user_id"],
                            f"{message}\nСумма: {updated['amount']} ₽",
                        )
                except Exception as exc:
                    logger.warning(f"Не удалось уведомить пользователя: {exc}")
            logger.info(
                f"✏️ Выплата {payout_id} обновлена — статус: {updates['status']}")
        else:
            logger.info(f"✏️ Выплата {payout_id} обновлена")
        return Payout(**updated)

    async def update_status(
        self, payout_id: str, status: str, notify: bool = True
    ) -> Optional[Payout]:
        self._repo.reload()
        updated = self._repo.update(payout_id, {"status": status})
        if not updated:
            return None
        logger.info(
            f"✏️ Выплата {payout_id} обновлена — статус: {status}")
        push_titles = {
            PAYOUT_STATUSES[1]: "✅ Заявка одобрена",
            PAYOUT_STATUSES[2]: "❌ Заявка отклонена",
            PAYOUT_STATUSES[3]: "📤 Выплата отправлена",
        }
        push_title = push_titles.get(status)
        if push_title:
            amount = updated.get("amount", "")
            push_body = f"Сумма: {amount} ₽"
            if self._push:
                try:
                    await self._push.send(
                        updated["user_id"], push_title, push_body
                    )
                except Exception as exc:
                    logger.warning(f"Не удалось отправить push: {exc}")
        if self._telegram and notify:
            try:
                tg_messages = {
                    PAYOUT_STATUSES[1]: "✅ Ваша заявка одобрена",
                    PAYOUT_STATUSES[2]: "❌ Ваша заявка отклонена",
                    PAYOUT_STATUSES[3]: "📤 Выплата отправлена",
                }
                message = tg_messages.get(status)
                if message:
                    await self._telegram.send_message_to_user(
                        updated["user_id"],
                        f"{message}\nСумма: {updated['amount']} ₽")
            except Exception as exc:
                logger.warning(f"Не удалось уведомить пользователя: {exc}")
        return Payout(**updated)

    async def bulk_update_status(self, ids: List[int], status: str) -> int:
        """Update status for multiple payouts. Never sends notifications."""
        if not ids:
            return 0
        self._repo.reload()
        count = 0
        for payout_id in ids:
            updated = self._repo.update(payout_id, {"status": status})
            if updated:
                count += 1
        logger.info(f"✏️ Массовое изменение статуса → {status}: {count} выплат")
        return count

    async def delete_payouts(self, ids: List[str]) -> None:
        if not ids:
            return
        self._repo.reload()
        self._repo.delete_many(ids)
        logger.info(f"🗑 Удалены выплаты: {', '.join(ids)}")

    async def delete_payout(self, payout_id: str) -> bool:
        self._repo.reload()
        deleted = self._repo.delete(payout_id)
        if deleted:
            logger.info(f"🗑 Удалена выплата {payout_id}")
        return deleted

    def get_payout_employee(self, payout_id: str) -> Optional[str]:
        """Return employee identifier associated with the payout."""
        self._repo.reload()
        for item in self._repo.load_all():
            if str(item.get("id")) == str(payout_id):
                user_id = item.get("user_id")
                return str(user_id) if user_id is not None else None
        return None

    async def list_active_payouts(self) -> List[Payout]:
        """Return payouts that are pending approval or already approved."""
        self._repo.reload()
        rows = self._repo.load_all()
        active = [
            r
            for r in rows
            if r.get("status") in PAYOUT_STATUSES[:2]
        ]
        return [Payout(**r) for r in active]

    async def export_to_pdf(
        self,
        employee_id: Optional[str] = None,
        payout_type: Optional[str] = None,
        status: Optional[str] = None,
        method: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Optional[str]:
        from app.services.excel import export_advances_to_pdf
        self._repo.reload()

        name = None
        if employee_id:
            rows = self._repo.list(employee_id=employee_id)
            if rows:
                name = rows[0].get("name")

        filename = f"payouts_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return export_advances_to_pdf(
            filter_type=payout_type,
            status=status,
            name=name,
            method=method,
            after_date=from_date,
            before_date=to_date,
            filename=filename,
        )

    async def list_control(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        payout_type: Optional[str] = None,
        method: Optional[str] = None,
        employee_id: Optional[str] = None,
        department: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        from datetime import datetime, timedelta
        from app.config import MAX_ADVANCE_AMOUNT_PER_MONTH
        from app.services.users import load_users_map

        self._repo.reload()

        all_rows = self._repo.load_all()
        rows = self._repo.list(
            employee_id,
            payout_type,
            status,
            method,
            date_from,
            date_to,
        )
        users = load_users_map()
        now = datetime.now()
        result: List[Dict[str, Any]] = []

        for item in rows:
            uid = str(item.get("user_id"))
            ts_str = item.get("timestamp")
            ts = None
            if ts_str:
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass
            user = users.get(uid, {})
            is_active = user.get("status", "active") == "active"
            warnings: list[str] = []

            # monthly total
            monthly_total = 0.0
            prev_count = 0
            for r in all_rows:
                if str(r.get("user_id")) != uid:
                    continue
                r_ts_str = r.get("timestamp")
                if not r_ts_str:
                    continue
                try:
                    r_ts = datetime.strptime(r_ts_str, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
                if ts and r_ts.year == ts.year and r_ts.month == ts.month:
                    monthly_total += float(r.get("amount") or 0)
                if ts and 0 < (ts - r_ts).total_seconds() <= 3 * 24 * 3600:
                    prev_count += 1

            if monthly_total > MAX_ADVANCE_AMOUNT_PER_MONTH:
                warnings.append("limit_exceeded")
            if item.get("status") == PAYOUT_STATUSES[0] and ts:
                if now - ts > timedelta(hours=48):
                    warnings.append("pending_too_long")
            if prev_count > 0:
                warnings.append("frequent_request")
            if user and user.get("bank") and item.get("bank") != user.get("bank"):
                warnings.append("changed_bank_data")
            if item.get("is_manual"):
                warnings.append("manual_created")
            if not is_active:
                warnings.append("inactive_employee")

            result.append(
                {
                    "id": str(item.get("id")),
                    "user_id": uid,
                    "name": item.get("name"),
                    "amount": float(item.get("amount") or 0),
                    "date": ts_str,
                    "status": item.get("status"),
                    "type": item.get("payout_type"),
                    "method": item.get("method"),
                    "warnings": warnings,
                    "is_manual": bool(item.get("is_manual")),
                    "is_employee_active": is_active,
                    "previous_requests_count": prev_count,
                    "previous_total_month": monthly_total,
                }
            )

        return result
