from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.schemas.asset import Asset, AssetCreate, AssetUpdate
from app.data.asset_repository import AssetRepository
from app.utils import is_valid_user_id
from app.utils.logger import log

if TYPE_CHECKING:
    from app.services.telegram_service import TelegramService


class AssetService:
    def __init__(
        self,
        repo: Optional[AssetRepository] = None,
        telegram: Optional["TelegramService"] = None,
    ) -> None:
        self._repo = repo or AssetRepository()
        self._telegram = telegram

    async def list_assets(self, employee_id: Optional[str] = None) -> List[Asset]:
        rows = self._repo.list(employee_id)
        return [Asset(**r) for r in rows]

    async def create_asset(self, data: AssetCreate) -> Asset:
        created = self._repo.create(data.model_dump())
        return Asset(**created)

    async def update_asset(self, item_id: str, data: AssetUpdate) -> Optional[Asset]:
        updated = self._repo.update(item_id, data.model_dump(exclude_none=True))
        return Asset(**updated) if updated else None

    async def delete_asset(self, item_id: str) -> None:
        self._repo.delete(item_id)

    async def bulk_delete(self, ids: list) -> int:
        count = 0
        for item_id in ids:
            self._repo.delete(str(item_id))
            count += 1
        return count

    async def notify_asset(self, item_id: str) -> dict:
        asset_dict = next(
            (i for i in self._repo.list() if str(i.get("id")) == str(item_id)),
            None,
        )
        if not asset_dict:
            return {"ok": False, "detail": "not_found"}

        if not self._telegram or not self._telegram.bot:
            return {"ok": False, "detail": "no_telegram"}

        employee_id = str(asset_dict.get("employee_id", ""))
        if not is_valid_user_id(employee_id):
            return {"ok": False, "detail": "no_telegram"}

        item_name = asset_dict.get("item_name", "")
        size = asset_dict.get("size") or ""
        quantity = asset_dict.get("quantity", 1)
        issue_date = asset_dict.get("issue_date", "")
        service_life = asset_dict.get("service_life")

        lines = ["📦 <b>Вам выдано имущество</b>", "", f"<b>{item_name}</b>"]
        if size:
            lines.append(f"Размер: {size}")
        lines.append(f"Количество: {quantity}")
        if issue_date:
            lines.append(f"Дата выдачи: {issue_date}")
        if service_life:
            lines.append(f"Срок службы: {service_life} мес.")
        lines += ["", "Нажмите кнопку ниже, чтобы подтвердить получение."]

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Подтвердить получение", callback_data=f"asset_ack_{item_id}")
        ]])

        try:
            await self._telegram.bot.send_message(
                chat_id=employee_id,
                text="\n".join(lines),
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            now = datetime.now().strftime("%d.%m.%Y %H:%M")
            self._repo.update(item_id, {"notified_at": now})
            return {"ok": True}
        except Exception as exc:
            log(f"Error sending asset notification to {employee_id}: {exc}")
            return {"ok": False, "detail": str(exc)}

    async def bulk_notify(self, ids: list) -> dict:
        sent = 0
        failed = 0
        for item_id in ids:
            result = await self.notify_asset(str(item_id))
            if result.get("ok"):
                sent += 1
            else:
                failed += 1
        return {"sent": sent, "failed": failed}

    def get_asset_employee(self, item_id: str) -> Optional[str]:
        for item in self._repo.list():
            if str(item.get("id")) == str(item_id):
                employee_id = item.get("employee_id")
                return str(employee_id) if employee_id is not None else None
        return None
