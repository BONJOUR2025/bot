"""Цех — приложение старшего мастера (workshop_service). Только чтение Агбиса.

Под отдельным правом «workshop»: его выдают человеку в «Доступе», должность
при этом не важна — старшим мастером может быть и мастер, и руководитель
отдела пошива. Единственная запись здесь — ручная отметка дня обучения
ученика, та же, что в панели «Мастера», и она пишется в нашу базу, не в Агбис.
"""
from __future__ import annotations

import asyncio
from datetime import date

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from app.services.access_control_service import ResolvedUser

from .dependencies import get_current_user, require_permission


scan_logger = logging.getLogger("master_scan")


class LeadScan(BaseModel):
    barcode: str
    action: str
    master_uid: int


class AttendanceMark(BaseModel):
    date: date
    note: str = ""


def create_workshop_router() -> APIRouter:
    router = APIRouter(
        prefix="/workshop",
        tags=["Workshop"],
        dependencies=[Depends(require_permission("workshop"))],
    )

    @router.get("/overview")
    async def overview(refresh: bool = Query(False)):
        from app.services.firebird_service import run_with_timeout
        from app.services.master_bot_service import StaleCacheError
        from app.services.workshop_service import get_overview

        try:
            return await run_with_timeout(get_overview, refresh, timeout=55)
        except StaleCacheError:
            raise HTTPException(503, "Данные обновляются, попробуйте через пару минут.")
        except asyncio.TimeoutError:
            raise HTTPException(504, "Сервер учёта сейчас занят, попробуйте через пару минут.")

    @router.post("/apprentices/{employee_id}/attendance")
    async def mark_apprentice(employee_id: str, data: AttendanceMark,
                              current: ResolvedUser = Depends(get_current_user)):
        """День обучения, которого нет на турникете (забыл пропуск, учился не в цеху)."""
        from app.data.apprentice_attendance_repository import get_apprentice_attendance_repository
        from app.data.employee_repository import EmployeeRepository
        from app.services.masters_service import APPRENTICE_POSITION
        from app.services.workshop_service import invalidate

        emp = EmployeeRepository().get_employee(employee_id)
        if emp is None:
            raise HTTPException(404, "Сотрудник не найден")
        if emp.position != APPRENTICE_POSITION:
            raise HTTPException(400, f"У сотрудника не должность «{APPRENTICE_POSITION}»")
        if data.date > date.today():
            raise HTTPException(400, "Нельзя отметить день, который ещё не наступил")
        author = getattr(current, "login", None) or getattr(current, "id", "workshop")
        rec = get_apprentice_attendance_repository().add_mark(
            employee_id, data.date, note=data.note.strip() or "отметил старший мастер", author=str(author),
        )
        invalidate()
        return rec

    # ── поиск заказа и карточка ───────────────────────────────────────
    async def _run(fn, *args):
        from app.services.firebird_service import run_with_timeout

        try:
            return await run_with_timeout(fn, *args, timeout=40)
        except asyncio.TimeoutError:
            raise HTTPException(504, "Сервер учёта сейчас занят, попробуйте через пару минут.")

    @router.get("/orders/find")
    async def find_order(q: str = Query(..., min_length=1, max_length=40)):
        from app.services import workshop_order_service as orders

        try:
            return await _run(orders.find, q)
        except orders.OrderNotFound as exc:
            raise HTTPException(404, str(exc))

    @router.get("/orders/{order_id}")
    async def order_card(order_id: int):
        from app.services import workshop_order_service as orders

        try:
            return await _run(orders.card, order_id)
        except orders.OrderNotFound as exc:
            raise HTTPException(404, str(exc))

    @router.get("/photos/{photo_id}/full")
    async def order_photo(photo_id: int, md5: str = Query(...)):
        """Фото изделия в полном размере — как у мастера, но по любому заказу."""
        from app.services import agbis_photos
        from app.services.firebird_service import get_firebird_service
        from app.services.workshop_order_service import photo_exists

        if not await _run(photo_exists, photo_id, md5):
            raise HTTPException(404, "Снимок не найден")
        try:
            data = await _run(get_firebird_service().get_order_photo_full_from_db, photo_id)
            if not data:
                data = await _run(agbis_photos.get_photo, md5)
        except agbis_photos.PhotoStorageError as exc:
            raise HTTPException(502, str(exc))
        return Response(content=data, media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=604800"})

    # ── вход и выход за мастера ───────────────────────────────────────
    def _masters_for_lead() -> dict[int, dict]:
        """За кого старший мастер может поставить отметку: сотрудники-мастера
        с кодом Агбиса в карточке. Не любой пользователь Агбиса — иначе
        отметку можно было бы записать на администратора или бухгалтера."""
        from app.services.master_bot_service import is_master_position
        from app.services.workshop_service import _people

        return {uid: p for uid, p in _people().items() if is_master_position(p.get("position"))}

    @router.get("/masters")
    async def lead_masters():
        people = await _run(_masters_for_lead)
        return sorted(({"master_uid": uid, "name": p["name"], "position": p["position"]}
                       for uid, p in people.items()), key=lambda m: m["name"])

    def _lead_check(data: LeadScan):
        from app.services import master_scan_service as scan

        if data.action not in scan.ACTIONS:
            raise HTTPException(400, "invalid_action")
        if len(scan.normalize_barcode(data.barcode)) not in (14, 18):
            raise HTTPException(400, scan.BARCODE_ERRORS["invalid_barcode"])
        masters = _masters_for_lead()
        if data.master_uid not in masters:
            raise HTTPException(400, "Выберите мастера из списка.")
        return masters[data.master_uid]

    @router.post("/scan/preview")
    async def lead_preview(data: LeadScan):
        from app.services import master_scan_service as scan

        master = await _run(_lead_check, data)
        result = await _run(scan.lead_preview, data.barcode, data.action, data.master_uid)
        if result is None:
            raise HTTPException(404, "Бирка не найдена в Агбисе.")
        return {**result, "master": master["name"]}

    @router.post("/scan/confirm")
    async def lead_confirm(data: LeadScan, current: ResolvedUser = Depends(get_current_user)):
        """Отметка за мастера — настоящая запись в Агбис (если включена).

        Каждая такая отметка уходит уведомлением в админский чат: это
        исключение из обычного порядка, и о нём должен знать руководитель.
        """
        from app.services import master_scan_service as scan
        from app.services.master_bot_service import invalidate_wip
        from app.services.workshop_service import invalidate

        master = await _run(_lead_check, data)
        lead = getattr(current, "display_name", None) or getattr(current, "login", None) or "старший мастер"
        result = await _run(scan.lead_confirm, data.barcode, data.action, data.master_uid, str(lead))
        if result is None:
            raise HTTPException(404, "Бирка не найдена в Агбисе.")
        written = [w["action"] for w in result["written"]]
        doc = result["service"].get("doc_num")
        scan_logger.info(
            "Отметка старшего мастера %s за %s (Агбис %s): %s, бирка %s, заказ %s — записано %s%s",
            lead, master["name"], data.master_uid, data.action, scan.normalize_barcode(data.barcode), doc,
            written or "ничего", f", сбой: {result['failed']}" if result["failed"] else "",
        )
        if written:
            invalidate_wip(data.master_uid)
            invalidate()
            try:
                from app.services.notify import send_notification

                what = " и ".join("вход" if a == "in" else "выход" for a in written)
                await send_notification(
                    f"🛠 <b>Отметка через старшего мастера</b>\n{lead} поставил {what} за "
                    f"{master['name']}\nЗаказ {doc}: {result['service'].get('name')}"
                    + (f"\n⚠️ Не записано: {result['failed']['reason']}" if result["failed"] else "")
                )
            except Exception:
                logging.getLogger(__name__).warning("Уведомление об отметке не отправлено", exc_info=True)
        return {**result, "master": master["name"]}

    return router
