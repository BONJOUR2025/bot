import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any

from app.schemas.payout import Payout, PayoutCreate, PayoutUpdate
from app.data.payout_repository import PayoutRepository
from app.data.employee_repository import EmployeeRepository
from . import vk_client
from .telegram_service import TelegramService
from app.core.enums import PAYOUT_STATUSES

import logging
from pathlib import Path

logger = logging.getLogger("payout_actions")
if not logger.handlers:
    Path("logs/payouts").mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler("logs/payouts/payout_actions.log", encoding="utf-8")
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
    def _to_amount(value) -> Optional[float]:
        """Parse a money value tolerantly: handles Decimal/float/int and strings
        like '5000', '5 000,00', '5000.00'. Returns the absolute value so an
        outgoing cash move stored as a negative still matches a positive payout.
        Returns None if it cannot be parsed."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return abs(float(value))
        try:
            from decimal import Decimal
            if isinstance(value, Decimal):
                return abs(float(value))
        except Exception:
            pass
        s = str(value).strip().replace(" ", "").replace(" ", "").replace(",", ".")
        try:
            return abs(float(s))
        except ValueError:
            return None

    @staticmethod
    def _fuzzy_find_cash_move(payout_dict: Dict) -> Optional[str]:
        """Find a Firebird cash movement matching payout by amount and exact date."""
        from datetime import date as date_cls
        try:
            from app.services.firebird_service import get_firebird_service
            ts = str(payout_dict.get("timestamp") or "")[:10]
            if not ts:
                return None
            payout_date = date_cls.fromisoformat(ts)
            payout_amount = PayoutService._to_amount(payout_dict.get("amount"))
            if payout_amount is None:
                return None
            moves = get_firebird_service().get_cash_moves(
                date_from=payout_date,
                date_to=payout_date,
            )
            for m in moves:
                move_date_str = str(m.get("DK_DATE") or "")[:10]
                try:
                    move_date = date_cls.fromisoformat(move_date_str)
                except ValueError:
                    continue
                move_amount = PayoutService._to_amount(m.get("SUMM"))
                if move_amount is None:
                    continue
                if move_date == payout_date and abs(payout_amount - move_amount) < 0.01:
                    return str(m.get("ID_KASSES_MOVE") or "")
        except Exception as exc:
            logger.warning(f"Cash move fuzzy match failed: {exc}")
        return None

    @staticmethod
    async def _notify_cash_move_linked(payout_dict: dict, move_id: str) -> None:
        try:
            from app.services.notify import send_notification
            name = payout_dict.get("payout_type") or "Выплата"
            amount = payout_dict.get("amount", "")
            await send_notification(
                f"🔗 <b>Выплата привязана к кассовому перемещению</b>\n"
                f"{name} · {amount} ₽ → перемещение #{move_id}"
            )
        except Exception:
            pass

    async def find_cash_move_for_payout(self, payout_id: int) -> Optional[str]:
        """Manually find and persist a cash movement link for an existing payout."""
        self._repo.reload()
        payout = next((p for p in self._repo.load_all() if p["id"] == payout_id), None)
        if not payout:
            return None
        if "кассы" not in (payout.get("method") or "").lower():
            return None
        # _fuzzy_find_cash_move does a blocking Firebird round trip (fdb.connect
        # + cursor.execute/fetchall — no asyncio.to_thread of its own). Called
        # directly like this, it runs on the event loop thread and freezes the
        # entire API for every user while it's in flight — including from
        # cash_move_auto_linker's background scan, which calls this every 5
        # minutes for every pending "Из кассы" payout, one at a time. Offload
        # it to a worker thread so a slow/contended Firebird moment only stalls
        # this one lookup, not the whole process.
        move_id = await asyncio.to_thread(self._fuzzy_find_cash_move, payout)
        if move_id:
            self._repo.update(str(payout_id), {"cash_move_id": move_id, "status": "Выплачено"})
            logger.info(f"🔗 Выплата {payout_id} привязана к движению {move_id}, статус → Выплачено")
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

        # Auto-link to cash movement for "Из кассы" payouts — see the
        # matching comment in find_cash_move_for_payout for why this needs
        # asyncio.to_thread: a blocking Firebird call here would otherwise
        # freeze the whole API for every user while a payout is being created.
        if not payout_dict["cash_move_id"] and "кассы" in (data.method or "").lower():
            move_id = await asyncio.to_thread(self._fuzzy_find_cash_move, payout_dict)
            if move_id:
                payout_dict["cash_move_id"] = move_id
                payout_dict["status"] = "Выплачено"
                asyncio.create_task(self._notify_cash_move_linked(payout_dict, move_id))

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
            new_status = updates["status"]
            status_messages = {
                PAYOUT_STATUSES[1]: "✅ Ваша заявка одобрена",
                PAYOUT_STATUSES[2]: "❌ Ваша заявка отклонена",
                PAYOUT_STATUSES[3]: "📤 Выплата отправлена",
            }
            message = status_messages.get(new_status) if notify else None
            if message:
                tg_text = f"{message}\nСумма: {updated['amount']} ₽"
                if self._telegram:
                    try:
                        await self._telegram.send_message_to_user(
                            updated["user_id"], tg_text)
                        delivery, error = "sent", None
                    except Exception as exc:
                        delivery, error = "failed", str(exc)
                        logger.warning(f"Не удалось уведомить пользователя: {exc}")
                else:
                    delivery, error = "skipped", "Telegram не настроен"
                self._log_notification(updated, new_status, "telegram", tg_text, delivery, error)
                await self._notify_vk(updated, new_status, tg_text)
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
            push_text = f"{push_title} — {push_body}"
            if self._push:
                try:
                    res = await self._push.send(
                        updated["user_id"], push_title, push_body
                    ) or {}
                    total, sent = res.get("total", 0), res.get("sent", 0)
                    if total == 0:
                        delivery, error = "skipped", "нет активных подписок"
                    elif sent > 0:
                        delivery, error = "sent", None
                    else:
                        delivery, error = "failed", "push не доставлен"
                except Exception as exc:
                    delivery, error = "failed", str(exc)
                    logger.warning(f"Не удалось отправить push: {exc}")
            else:
                delivery, error = "skipped", "push не настроен"
            self._log_notification(updated, status, "push", push_text, delivery, error)
        if notify:
            tg_messages = {
                PAYOUT_STATUSES[1]: "✅ Ваша заявка одобрена",
                PAYOUT_STATUSES[2]: "❌ Ваша заявка отклонена",
                PAYOUT_STATUSES[3]: "📤 Выплата отправлена",
            }
            message = tg_messages.get(status)
            if message:
                tg_text = f"{message}\nСумма: {updated['amount']} ₽"
                if self._telegram:
                    try:
                        await self._telegram.send_message_to_user(
                            updated["user_id"], tg_text)
                        delivery, error = "sent", None
                    except Exception as exc:
                        delivery, error = "failed", str(exc)
                        logger.warning(f"Не удалось уведомить пользователя: {exc}")
                else:
                    delivery, error = "skipped", "Telegram не настроен"
                self._log_notification(updated, status, "telegram", tg_text, delivery, error)
                await self._notify_vk(updated, status, tg_text)
        return Payout(**updated)

    async def _notify_vk(self, payout, status: str, text: str) -> None:
        """Send the same status text over VK, if this employee has a linked
        vk_id — independent of (and in addition to) the Telegram attempt
        above, since an employee can have both channels linked at once."""
        employee = EmployeeRepository().get_employee(str(payout.get("user_id", "")))
        vk_id = getattr(employee, "vk_id", "") if employee else ""
        if not vk_id:
            self._log_notification(payout, status, "vk", text, "skipped", "VK не привязан")
            return
        message_id = await vk_client.send_message(vk_id, text)
        if message_id is not None:
            self._log_notification(payout, status, "vk", text, "sent", None)
        else:
            self._log_notification(payout, status, "vk", text, "failed", "Ошибка отправки VK")

    @staticmethod
    def _log_notification(payout, status, channel, message, delivery, error):
        """Record a notification attempt in the payout journal (best-effort)."""
        try:
            from app.data.payout_notification_repository import (
                get_payout_notification_repository,
            )
            get_payout_notification_repository().add_entry(
                payout_id=payout.get("id"),
                user_id=str(payout.get("user_id", "")),
                recipient_name=payout.get("name", ""),
                status=status,
                channel=channel,
                message=message,
                delivery=delivery,
                error=error,
                amount=payout.get("amount"),
            )
        except Exception as exc:
            logger.warning(f"Не удалось записать журнал уведомления: {exc}")

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

    async def link_cash_move(self, payout_id: str, move_id: str) -> Optional[Payout]:
        self._repo.reload()
        updated = self._repo.update(payout_id, {"cash_move_id": move_id})
        if updated:
            logger.info(f"🔗 Выплата {payout_id} вручную привязана к движению {move_id}")
            return Payout(**updated)
        return None

    async def unlink_cash_move(self, payout_id: str) -> Optional[Payout]:
        self._repo.reload()
        updated = self._repo.unlink_cash_move(payout_id)
        if updated:
            logger.info(f"🔓 Выплата {payout_id} отвязана от движения")
            return Payout(**updated)
        return None

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
