"""Кабинет точки на рабочем ПК салона (/admin/point).

Вход не по логину человека, а по ключу компьютера: руководитель в «Салонах»
выдаёт одноразовый код, на ПК точки его вводят один раз. Дальше каждый запрос
несёт заголовок X-Point-Token, и точка берётся из ключа — чужую точку этим
ключом не открыть. Зарплат, выручки сети и прочего личного здесь нет.
"""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel

from .dependencies import require_permission

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL = 90  # секунд: список выдачи смотрят весь день, Агбис не дёргаем на каждый клик


class ActivateIn(BaseModel):
    code: str
    label: str = ""


class AskIn(BaseModel):
    question: str


class CallIn(BaseModel):
    result: str
    note: str = ""


def _salon(salon_id: str):
    from app.data.salon_repository import get_salon_repository

    return get_salon_repository().get(salon_id)


def point_device(x_point_token: str = Header("", alias="X-Point-Token")):
    from app.data.point_device_repository import PointDeviceRepository

    device = PointDeviceRepository().by_token(x_point_token)
    if device is None:
        raise HTTPException(status_code=401, detail="Компьютер не подключён к кабинету точки.")
    salon = _salon(device["salon_id"])
    if salon is None or salon.status != "active":
        raise HTTPException(status_code=403, detail="Точка не найдена или закрыта.")
    return device, salon


async def _run(fn, *args):
    from app.services.firebird_service import run_with_timeout

    try:
        return await run_with_timeout(fn, *args, timeout=45)
    except asyncio.TimeoutError:
        raise HTTPException(504, "Сервер учёта сейчас занят, попробуйте через минуту.")


def create_point_admin_router() -> APIRouter:
    """Выдача кодов и список подключённых ПК — для руководителя, под правом salons."""
    router = APIRouter(prefix="/salons", tags=["Point"])

    @router.post("/{salon_id}/point-code")
    async def issue_code(salon_id: str, current=Depends(require_permission("salons"))):
        from app.data.point_device_repository import PointDeviceRepository

        if _salon(salon_id) is None:
            raise HTTPException(404, "Салон не найден")
        author = getattr(current, "display_name", None) or getattr(current, "login", None) or "admin"
        return PointDeviceRepository().issue_code(salon_id, str(author))

    @router.get("/{salon_id}/point-devices")
    async def list_devices(salon_id: str, current=Depends(require_permission("salons"))):
        from app.data.point_device_repository import PointDeviceRepository

        return PointDeviceRepository().list(salon_id)

    @router.delete("/{salon_id}/point-devices/{device_id}")
    async def revoke(salon_id: str, device_id: str, current=Depends(require_permission("salons"))):
        from app.data.point_device_repository import PointDeviceRepository

        if not PointDeviceRepository().revoke(device_id):
            raise HTTPException(404, "Компьютер не найден")
        return {"ok": True}

    return router


def create_point_router() -> APIRouter:
    router = APIRouter(prefix="/point", tags=["Point"])

    @router.post("/activate")
    async def activate(data: ActivateIn):
        from app.data.point_device_repository import PointDeviceRepository

        res = PointDeviceRepository().activate(data.code, data.label)
        if res is None:
            raise HTTPException(400, "Код неверный или устарел. Попросите руководителя выдать новый.")
        token, device = res
        salon = _salon(device["salon_id"])
        return {"token": token, "salon": {"id": salon.id, "name": salon.name} if salon else None}

    @router.get("/me")
    async def me(dev=Depends(point_device)):
        device, salon = dev
        return {"salon": {"id": salon.id, "name": salon.name, "address": salon.address, "phone": salon.phone,
                          "hours_weekday": salon.work_hours_weekday, "hours_weekend": salon.work_hours_weekend},
                "device": {"id": device["id"], "label": device.get("label")}}

    @router.get("/today")
    async def today(refresh: bool = Query(False), dev=Depends(point_device)):
        from app.data.point_device_repository import PointCallRepository
        from app.services import point_service

        device, salon = dev
        hit = _CACHE.get(salon.id)
        if hit and not refresh and time.time() - hit[0] < _TTL:
            data, at = hit[1], hit[0]
        else:
            data = await _run(point_service.orders, salon)
            at = time.time()
            _CACHE[salon.id] = (at, data)
        # Отметки звонков — свежие всегда: только что отмеченный звонок должен
        # сразу уйти из «позвонить», не дожидаясь кэша.
        ids = [r["order_id"] for r in data["ready"]] + [r["order_id"] for r in data["due"]]
        calls = PointCallRepository().last_for(ids)
        for r in data["ready"] + data["due"]:
            r["call"] = calls.get(r["order_id"])
        return {**data, "shift": point_service.shift(salon),
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(at))}

    @router.post("/orders/{order_id}/call")
    async def mark_call(order_id: int, data: CallIn, dev=Depends(point_device)):
        from app.data.point_device_repository import PointCallRepository

        device, salon = dev
        if data.result not in PointCallRepository.RESULTS:
            raise HTTPException(400, "Неизвестный результат звонка")
        return PointCallRepository().add(order_id, data.result, data.note, salon.id, device["id"])

    # ── поиск заказа и карточка: те же, что в «Цехе», но по ключу точки ──
    @router.get("/orders/find")
    async def find(q: str = Query(..., min_length=1, max_length=40), dev=Depends(point_device)):
        from app.services import workshop_order_service as orders

        try:
            return await _run(orders.find, q)
        except orders.OrderNotFound as exc:
            raise HTTPException(404, str(exc))

    @router.get("/orders/{order_id}")
    async def card(order_id: int, dev=Depends(point_device)):
        from app.services import workshop_order_service as orders

        try:
            return await _run(orders.card, order_id)
        except orders.OrderNotFound as exc:
            raise HTTPException(404, str(exc))

    # ── приём, логистика, график ──────────────────────────────────────
    @router.get("/accepted")
    async def accepted(dev=Depends(point_device)):
        from app.services import point_service

        return await _run(point_service.accepted_today, dev[1])

    @router.get("/logistics")
    async def logistics(dev=Depends(point_device)):
        from app.services import point_service

        return await _run(point_service.logistics, dev[1])

    @router.get("/schedule")
    async def schedule(dev=Depends(point_device)):
        from app.services import point_service

        return await point_service.week_schedule(dev[1])

    # ── клиенты: поиск, история, пароль от личного кабинета ───────────
    @router.get("/clients/search")
    async def clients_search(q: str = Query(..., min_length=2, max_length=60), dev=Depends(point_device)):
        from app.services.firebird_service import get_firebird_service

        return await _run(get_firebird_service().search_clients, q.strip(), 20)

    @router.get("/clients/{contragent_id}")
    async def client_profile(contragent_id: int, dev=Depends(point_device)):
        from app.services.firebird_service import get_firebird_service

        profile = await _run(get_firebird_service().get_client_profile, contragent_id)
        if not profile:
            raise HTTPException(404, "Клиент не найден")
        # Сумма всех покупок клиента — коммерческая сводка для руководителя,
        # на стойке она ни к чему: оставляем число заказов и их список.
        profile.pop("total_spent", None)
        profile.pop("avg_check", None)
        profile["orders"] = list(reversed(profile.get("orders") or []))[:30]
        return profile

    @router.get("/clients-lk-password")
    async def lk_password(phone: str = Query(..., min_length=5, max_length=30), dev=Depends(point_device)):
        from app.services.firebird_service import get_firebird_service

        return await _run(get_firebird_service().get_client_lk_passwords, phone)

    # ── база знаний и помощник ───────────────────────────────────────
    @router.get("/kb")
    async def kb(dev=Depends(point_device)):
        from app.services import point_service

        return point_service.kb_documents()

    @router.post("/kb/ask")
    async def kb_ask(data: AskIn, dev=Depends(point_device)):
        from app.services import point_service

        q = (data.question or "").strip()
        if len(q) < 3:
            raise HTTPException(400, "Задайте вопрос подробнее.")
        try:
            answer = await asyncio.to_thread(point_service.kb_ask, q[:1000], dev[1].name)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc))
        return {"answer": answer}

    @router.get("/photos/{photo_id}/full")
    async def photo(photo_id: int, md5: str = Query(...), dev=Depends(point_device)):
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
        return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=604800"})

    return router
