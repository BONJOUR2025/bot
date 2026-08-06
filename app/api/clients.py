"""API endpoints for the client CRM view (Agbis contragents)."""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .dependencies import require_permission


def create_clients_router() -> APIRouter:
    router = APIRouter(
        prefix="/clients",
        tags=["Clients"],
        dependencies=[Depends(require_permission("payroll"))],
    )

    @router.get("/search")
    async def search_clients(q: str = Query(..., min_length=2)):
        """Search Agbis clients by name or phone."""
        from app.services.firebird_service import get_firebird_service, run_with_timeout, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")

        try:
            svc = get_firebird_service()
            # Not cached: a free-text query is an unbounded key space, and
            # this already has its own 45s in-process cache for the
            # type-ahead's repeated keystrokes.
            return await run_with_timeout(svc.search_clients, q)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/churning")
    async def get_churning_clients(
        lookback_days: int = Query(default=365, ge=30, le=1095),
        min_orders: int = Query(default=3, ge=2, le=50),
    ):
        """Return clients who used to order regularly and have gone quiet."""
        from app.services import fdb_cache
        from app.services.firebird_service import run_with_timeout, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")

        try:
            return await run_with_timeout(
                fdb_cache.get_or_compute, "clients.churning", (lookback_days, min_orders),
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/{contragent_id}/orders/{doc_num}/items")
    async def get_order_items(contragent_id: int, doc_num: str):
        """Return the services/goods inside one client order."""
        from app.services.firebird_service import get_firebird_service, run_with_timeout, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")

        try:
            svc = get_firebird_service()
            return await run_with_timeout(svc.get_order_items, contragent_id, doc_num)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/{contragent_id}/orders/{doc_num}/photos")
    async def get_order_photos(contragent_id: int, doc_num: str):
        """Снимки заказа, сгруппированные по изделиям, с миниатюрой в виде
        data URI прямо в ответе.

        Специально не отдельным адресом на фото: у заказа бывает под 90
        снимков, и 90 независимых <img>, каждый со своим запросом к
        Firebird, — тот самый паттерн параллельных подключений, что уронил
        сервер 18.07.2026. Один запрос, читающий N маленьких блобов из уже
        открытого подключения, ничего не стоит по сравнению с этим.
        Полноразмерный снимок в этой базе не хранится вовсе и тянется
        отдельно, по клику — см. app/services/agbis_photos.
        """
        from app.services.firebird_service import get_firebird_service, run_with_timeout, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")
        try:
            svc = get_firebird_service()
            return await run_with_timeout(svc.get_order_photos, contragent_id, doc_num)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Попробуйте снова.")

    @router.get("/photos/{photo_id}/full")
    async def get_photo_full(photo_id: int, md5: str = Query(...)):
        """Полноразмерный снимок.

        Проксируется, а не отдаётся ссылкой: доступ к агенту хранилища идёт
        по SessionID, равнозначному паролю сервисной учётки, и он не должен
        попадать в браузер.

        `md5` приходит из списка снимков, а не подставляется клиентом
        произвольно: сначала проверяем, что такой снимок с таким хешем
        действительно есть в базе, и только потом идём за файлом.
        """
        from fastapi import Response
        from app.services import agbis_photos
        from app.services.firebird_service import get_firebird_service, run_with_timeout, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")

        svc = get_firebird_service()

        def _verify() -> bool:
            from app.services.firebird_service import _connect
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(
                    "SELECT md5_checksum FROM doc_order_serv_photos WHERE id = ?", (photo_id,)
                )
                row = cur.fetchone()
            finally:
                con.close()
            stored = row[0] if row else None
            if isinstance(stored, bytes):
                stored = stored.decode("utf-8", "replace")
            return bool(stored) and stored.strip().upper() == (md5 or "").strip().upper()

        try:
            if not await run_with_timeout(_verify):
                raise HTTPException(status_code=404, detail="Снимок не найден")
            # Довольно старые снимки ещё лежат в самой базе — тогда агент не нужен.
            data = await run_with_timeout(svc.get_order_photo_full_from_db, photo_id)
            if not data:
                data = await run_with_timeout(agbis_photos.get_photo, md5, timeout=90)
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Хранилище фотографий не ответило вовремя. Попробуйте ещё раз.",
            )
        except agbis_photos.PhotoStorageError as exc:
            # Хранилище — компьютер в салоне; он может быть выключен.
            raise HTTPException(status_code=502, detail=str(exc))

        return Response(content=data, media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=604800"})

    @router.get("/{contragent_id}")
    async def get_client_profile(contragent_id: int):
        """Return one client's full order history, LTV, average check, last visit."""
        from app.services.firebird_service import get_firebird_service, run_with_timeout, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")

        try:
            svc = get_firebird_service()
            profile = await run_with_timeout(svc.get_client_profile, contragent_id)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Попробуйте снова.")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        if profile is None:
            raise HTTPException(status_code=404, detail="Клиент не найден")
        return profile

    return router
