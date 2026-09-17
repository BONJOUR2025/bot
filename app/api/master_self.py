"""Кабинет мастера — в вебе и в приложении «BONJOUR Мастер».

Те же данные, что раздел мастера в Telegram-боте (master_bot_service), и по
тем же правилам: мастер видит только свои сканы, опознаётся по коду Агбиса из
карточки, а отчёт берётся из прогретого кэша, а не считается на каждый запрос.
Отдельно от /masters (сводка по всем мастерам под правом payroll): здесь права
не нужны, потому что чужого сюда не попадает по построению — id берётся из
сессии, а не из запроса.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.services.access_control_service import ResolvedUser

from .dependencies import get_current_user

PERIODS = ("month", "prev_month")


def create_master_self_router() -> APIRouter:
    router = APIRouter(prefix="/masters/me", tags=["Masters"])

    def _master(current: ResolvedUser):
        from app.services.master_bot_service import resolve_master

        if not current.employee_id:
            raise HTTPException(status_code=403, detail="not_an_employee")
        master = resolve_master(current.employee_id)
        if master is None:
            raise HTTPException(status_code=404, detail="not_a_master")
        return master

    async def _run(fn, *args):
        from app.services.firebird_service import run_with_timeout
        from app.services.master_bot_service import StaleCacheError

        try:
            return await run_with_timeout(fn, *args, timeout=55)
        except StaleCacheError:
            raise HTTPException(
                status_code=503,
                detail="Данные обновляются, попробуйте через пару минут.",
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Сервер учёта сейчас занят, попробуйте через пару минут.",
            )

    @router.get("/earnings")
    async def get_my_earnings(
        period: str = Query("month"),
        current: ResolvedUser = Depends(get_current_user),
    ) -> dict:
        from app.services.master_bot_service import get_earnings

        if period not in PERIODS:
            raise HTTPException(status_code=400, detail="invalid_period")
        master = _master(current)
        report = await _run(get_earnings, master, period)
        return {**report, "name": master.name, "position": master.position}

    @router.get("/wip")
    async def get_my_wip(current: ResolvedUser = Depends(get_current_user)) -> dict:
        from app.services.master_bot_service import get_wip

        return {"items": await _run(get_wip, _master(current))}

    @router.get("/advance-cap")
    async def get_my_advance_cap(current: ResolvedUser = Depends(get_current_user)) -> dict:
        from app.services.master_bot_service import get_advance_cap

        return await _run(get_advance_cap, _master(current))

    # ── Вход / выход по бирке ─────────────────────────────────────────
    # lookup и preview только читают Агбис. confirm пишет скан, если в .env
    # включён AGBIS_SCAN_WRITE, иначе отвечает как preview
    # (см. master_scan_service).
    import logging

    from fastapi import Body

    scan_logger = logging.getLogger("master_scan")

    def _scan_error(exc: ValueError) -> HTTPException:
        from app.services.master_scan_service import BARCODE_ERRORS

        return HTTPException(status_code=400, detail=BARCODE_ERRORS.get(str(exc), "Не удалось прочитать бирку."))

    @router.get("/scan/mode")
    async def scan_mode(current: ResolvedUser = Depends(get_current_user)) -> dict:
        """Пишет ли скан в Агбис — чтобы страница знала режим ещё до первой бирки."""
        from app.services import master_scan_service as scan

        _master(current)
        return {"dry_run": not scan.write_enabled()}

    @router.get("/scan/lookup")
    async def scan_lookup(
        barcode: str = Query(...),
        current: ResolvedUser = Depends(get_current_user),
    ) -> dict:
        from app.services import master_scan_service as scan

        master = _master(current)
        try:
            result = await _run(scan.describe, master, barcode)
        except scan.BarcodeError as exc:
            raise _scan_error(exc)
        if result is None:
            raise HTTPException(status_code=404, detail="Бирка не найдена в Агбисе. Проверьте номер под штрихкодом.")
        return result

    @router.post("/scan/preview")
    async def scan_preview(
        barcode: str = Body(...),
        action: str = Body(...),
        current: ResolvedUser = Depends(get_current_user),
    ) -> dict:
        from app.services import master_scan_service as scan

        if action not in scan.ACTIONS:
            raise HTTPException(status_code=400, detail="invalid_action")
        master = _master(current)
        try:
            result = await _run(scan.plan, master, barcode, action)
        except scan.BarcodeError as exc:
            raise _scan_error(exc)
        if result is None:
            raise HTTPException(status_code=404, detail="Бирка не найдена в Агбисе. Проверьте номер под штрихкодом.")
        scan_logger.info(
            "Пробный скан: %s (Агбис %s) %s, бирка %s, заказ %s — %s",
            master.name, master.agbis_user_id, action, scan.normalize_barcode(barcode),
            result["service"].get("doc_num"), "разрешён" if result["allowed"] else "; ".join(result["blockers"]),
        )
        return result

    @router.post("/scan/confirm")
    async def scan_confirm(
        barcode: str = Body(...),
        action: str = Body(...),
        current: ResolvedUser = Depends(get_current_user),
    ) -> dict:
        from app.services import master_scan_service as scan

        if action not in scan.ACTIONS:
            raise HTTPException(status_code=400, detail="invalid_action")
        master = _master(current)
        try:
            result = await _run(scan.confirm, master, barcode, action)
        except scan.BarcodeError as exc:
            raise _scan_error(exc)
        if result is None:
            raise HTTPException(status_code=404, detail="Бирка не найдена в Агбисе. Проверьте номер под штрихкодом.")
        if result["dry_run"]:
            outcome = "пробно, " + ("разрешён" if result["allowed"] else "; ".join(result["blockers"]))
        elif result.get("written"):
            outcome = f"ЗАПИСАН в Агбис: {result['ids']}"
        else:
            outcome = "не записан: " + "; ".join(result["blockers"])
        scan_logger.info(
            "Скан: %s (Агбис %s) %s, бирка %s, заказ %s — %s",
            master.name, master.agbis_user_id, action, scan.normalize_barcode(barcode),
            result["service"].get("doc_num"), outcome,
        )
        return result

    return router
