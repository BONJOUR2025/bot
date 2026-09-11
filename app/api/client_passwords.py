"""Восстановление пароля от личного кабинета клиента по номеру телефона.

Отдельно от менеджера паролей (`/passwords`) и от клиентского CRM
(`/clients`): доступ к паролям клиентов — чувствительная операция, поэтому
эндпоинт закрыт правом `passwords`, а не общим `payroll`.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from .dependencies import require_permission


def create_client_password_router() -> APIRouter:
    router = APIRouter(
        prefix="/client-passwords",
        tags=["ClientPasswords"],
        dependencies=[Depends(require_permission("passwords"))],
    )

    @router.get("/lookup")
    async def lookup(phone: str = Query(..., min_length=4)):
        """Найти клиента(ов) по телефону и вернуть пароль(и) от ЛК."""
        from app.services.firebird_service import (
            get_firebird_service,
            run_with_timeout,
            FIREBIRD_AVAILABLE,
        )

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")

        try:
            svc = get_firebird_service()
            return await run_with_timeout(svc.get_client_lk_passwords, phone)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return router
