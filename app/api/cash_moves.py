from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from .dependencies import get_current_user, require_permission

VALID_PREFIXES = [
    "ЗАРПЛАТА_", "ЗП_", "ЛОГИСТИКА", "МАТЕРИАЛЫ_", "УБОРКА_", "ЧАЙ_",
    "АПТЕЧКА_", "ВОЗВРАТ_", "КАНЦТОВАРЫ_", "УПАКОВКА_", "ИНКАССАЦИЯ_",
]

DEP_MAP: dict[str, str] = {
    "17": "Охта-Молл",
    "11": "Меркурий",
    "7": "Пассаж",
    "5": "Академ Парк",
    "3": "Озерки",
    "8": "Бестужевская",
}

USERS_MAP: dict[str, str] = {
    "110275": "Вера 0102",
    "110171": "Анастасия 2602",
    "110158": "Арина 7272",
    "110273": "Александр 1505",
    "110221": "Эмиль 2404",
    "111111": "Полина 5984",
    "110276": "Наталья 0704",
    "1136": "Катя 2201",
    "110146": "Лали 1606",
    "110145": "Екатерина 0104",
    "110265": "Ирина 2006",
    "110255": "Полина 1802",
    "110150": "Вероника 1996",
    "1134": "Ира 2405",
    "110287": "Юля 3007",
    "110222": "Алекс 2104",
    "109110": "Марина 0208",
}


def _has_valid_prefix(basis: str | None) -> bool:
    if not basis:
        return False
    t = str(basis).strip().upper()
    return any(t.startswith(p) for p in VALID_PREFIXES)


def create_cash_moves_router() -> APIRouter:
    router = APIRouter(prefix="/cash-moves", tags=["cash-moves"])
    perm = require_permission("cash-moves")

    @router.get("/meta")
    async def meta(_=Depends(perm)):
        return {
            "dep_map": DEP_MAP,
            "users_map": USERS_MAP,
            "valid_prefixes": VALID_PREFIXES,
        }

    @router.get("/")
    async def list_cash_moves(
        date_from: date | None = Query(None),
        date_to: date | None = Query(None),
        _=Depends(perm),
    ):
        from app.services.firebird_service import get_firebird_service
        rows = get_firebird_service().get_cash_moves(date_from=date_from, date_to=date_to)
        for r in rows:
            dep_id = str(r.get("DEP_SRC_ID") or "")
            usr_id = str(r.get("OWN_USR_ID") or "")
            r["dep_name"] = DEP_MAP.get(dep_id, dep_id or "—")
            r["user_name"] = USERS_MAP.get(usr_id, usr_id or "—")
            r["prefix_ok"] = _has_valid_prefix(r.get("BASIS"))
        return rows

    return router
