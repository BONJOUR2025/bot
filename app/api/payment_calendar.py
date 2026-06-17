from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from .dependencies import require_permission
from app.data.payment_calendar_repository import (
    PaymentCalendarRepository,
    get_payment_calendar_repository,
)


class CategoryCreate(BaseModel):
    name: str


class CategoryUpdate(BaseModel):
    name: str


class ScheduleCreate(BaseModel):
    name: str
    planned_amount: float
    day_of_month: int
    category: str = ""
    responsible_name: str = ""
    responsible_tg_id: str = ""
    notify_days_before: int = 3
    note: str = ""
    objects: List[str] = []
    seller: str = ""
    pay_from: str = ""


class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    planned_amount: Optional[float] = None
    day_of_month: Optional[int] = None
    category: Optional[str] = None
    responsible_name: Optional[str] = None
    responsible_tg_id: Optional[str] = None
    notify_days_before: Optional[int] = None
    is_active: Optional[bool] = None
    note: Optional[str] = None
    objects: Optional[List[str]] = None
    seller: Optional[str] = None
    pay_from: Optional[str] = None


class PayBody(BaseModel):
    actual_amount: Optional[float] = None
    comment: Optional[str] = None


def create_payment_calendar_router(repo: Optional[PaymentCalendarRepository] = None) -> APIRouter:
    if repo is None:
        repo = get_payment_calendar_repository()

    router = APIRouter(prefix="/payment-calendar", tags=["payment-calendar"])
    perm = require_permission("payment-calendar")

    @router.get("/categories")
    async def list_categories(_=Depends(perm)):
        return repo.list_categories()

    @router.post("/categories")
    async def create_category(body: CategoryCreate, _=Depends(perm)):
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "name required")
        return repo.create_category(name)

    @router.patch("/categories/{category_id}")
    async def update_category(category_id: int, body: CategoryUpdate, _=Depends(perm)):
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "name required")
        result = repo.update_category(category_id, name)
        if result is None:
            raise HTTPException(404, "not found")
        return result

    @router.delete("/categories/{category_id}")
    async def delete_category(category_id: int, _=Depends(perm)):
        if not repo.delete_category(category_id):
            raise HTTPException(404, "not found")
        return {"ok": True}

    @router.get("/schedules")
    async def list_schedules(_=Depends(perm)):
        return repo.list_schedules()

    @router.post("/schedules")
    async def create_schedule(body: ScheduleCreate, _=Depends(perm)):
        if not 1 <= body.day_of_month <= 31:
            raise HTTPException(400, "day_of_month must be 1–31")
        return repo.create_schedule(body.model_dump())

    @router.patch("/schedules/{schedule_id}")
    async def update_schedule(schedule_id: int, body: ScheduleUpdate, _=Depends(perm)):
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        result = repo.update_schedule(schedule_id, updates)
        if result is None:
            raise HTTPException(404, "not found")
        return result

    @router.delete("/schedules/{schedule_id}")
    async def delete_schedule(schedule_id: int, _=Depends(perm)):
        if not repo.delete_schedule(schedule_id):
            raise HTTPException(404, "not found")
        return {"ok": True}

    @router.post("/schedules/{schedule_id}/send-to-cashier")
    async def send_to_cashier(
        schedule_id: int,
        invoice: Optional[UploadFile] = File(None),
        notify: bool = Form(True),
        _=Depends(perm),
    ):
        schedule = repo.get_schedule(schedule_id)
        if schedule is None:
            raise HTTPException(404, "not found")

        invoice_path: Optional[Path] = None
        if invoice is not None and invoice.filename:
            content = await invoice.read()
            upload_dir = Path("static/uploads/payment_calendar")
            upload_dir.mkdir(parents=True, exist_ok=True)
            ext = Path(invoice.filename).suffix or ""
            invoice_path = upload_dir / f"{schedule_id}{ext}"
            invoice_path.write_bytes(content)
            schedule = repo.update_schedule(
                schedule_id, {"invoice_file_url": f"/static/uploads/payment_calendar/{schedule_id}{ext}"}
            )
        elif schedule.get("invoice_file_url"):
            invoice_path = Path(schedule["invoice_file_url"].lstrip("/"))

        if not notify:
            return {"ok": True, "schedule": schedule}

        from app.services.config_service import ConfigService
        chat_id = str(ConfigService().load().get("payment_calendar_cashier_chat_id") or "").strip()
        if not chat_id:
            from app.utils.logger import log_payment_calendar
            log_payment_calendar(
                f"send-to-cashier schedule_id={schedule_id}: payment_calendar_cashier_chat_id не настроен"
            )
            raise HTTPException(400, "Telegram ID кассира не настроен (Настройки → Telegram)")

        def esc(v) -> str:
            return str(v or "—").replace("`", "'")

        amount = f"{schedule['planned_amount']:,.0f}".replace(",", " ")
        text = (
            "📋 *Просьба оплатить счёт*\n\n"
            "```\n"
            f"Товар/Услуга : {esc(schedule['name'])}\n"
            f"Продавец     : {esc(schedule.get('seller'))}\n"
            f"Сумма        : {amount} ₽\n"
            f"Платим от    : {esc(schedule.get('pay_from'))}\n"
            "```"
        )

        year_month = datetime.utcnow().strftime("%Y-%m")
        record = repo.get_or_create_record(schedule_id, year_month)
        reply_markup = {
            "inline_keyboard": [[{"text": "✅ Оплачено", "callback_data": f"paycal_paid_{record['id']}"}]]
        }

        from app.services.notify import send_chat_document, send_chat_message
        if invoice_path and invoice_path.exists():
            sent = await send_chat_document(
                chat_id, str(invoice_path), caption=text, parse_mode="Markdown", reply_markup=reply_markup
            )
        else:
            sent = await send_chat_message(chat_id, text, parse_mode="Markdown", reply_markup=reply_markup)

        return {"ok": sent, "schedule": schedule}

    @router.get("/month/{year_month}")
    async def get_month(year_month: str, _=Depends(perm)):
        try:
            datetime.strptime(year_month, "%Y-%m")
        except ValueError:
            raise HTTPException(400, "year_month must be YYYY-MM")
        return repo.get_or_create_records_for_month(year_month)

    @router.post("/records/{record_id}/pay")
    async def mark_paid(record_id: int, body: PayBody, _=Depends(perm)):
        updates: dict = {"status": "paid", "paid_at": datetime.utcnow()}
        if body.actual_amount is not None:
            updates["actual_amount"] = body.actual_amount
        if body.comment is not None:
            updates["comment"] = body.comment
        result = repo.update_record(record_id, updates)
        if result is None:
            raise HTTPException(404, "not found")
        return result

    @router.post("/records/{record_id}/skip")
    async def mark_skipped(record_id: int, _=Depends(perm)):
        result = repo.update_record(record_id, {"status": "skipped"})
        if result is None:
            raise HTTPException(404, "not found")
        return result

    @router.post("/records/{record_id}/reset")
    async def reset_record(record_id: int, _=Depends(perm)):
        result = repo.update_record(
            record_id,
            {"status": "pending", "paid_at": None, "actual_amount": None, "comment": None},
        )
        if result is None:
            raise HTTPException(404, "not found")
        return result

    return router
