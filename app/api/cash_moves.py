import asyncio
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .dependencies import require_permission
from app.data.cash_category_repository import CashCategoryRepository, get_cash_category_repository
from app.data.cash_config_repository import CashConfigRepository, get_cash_config_repository


class CategoryCreate(BaseModel):
    name: str
    prefixes: List[str] = []


class CategoryUpdate(BaseModel):
    new_name: Optional[str] = None
    prefixes: Optional[List[str]] = None


class PrefixBody(BaseModel):
    prefix: str


class AssignBody(BaseModel):
    record_id: str
    category: str
    add_prefix: Optional[str] = None


class MappingEntry(BaseModel):
    id: str
    name: str


def create_cash_moves_router(
    repo: Optional[CashCategoryRepository] = None,
    cfg: Optional[CashConfigRepository] = None,
) -> APIRouter:
    if repo is None:
        repo = get_cash_category_repository()
    if cfg is None:
        cfg = get_cash_config_repository()

    router = APIRouter(prefix="/cash-moves", tags=["cash-moves"])
    perm = require_permission("cash-moves")

    # ── Meta ─────────────────────────────────────────────────────────

    @router.get("/meta")
    async def meta(_=Depends(perm)):
        return {
            "categories": repo.list_categories(),
            "valid_prefixes": repo.all_prefixes(),
            "branches": cfg.get_branches(),
        }

    # ── Categories ───────────────────────────────────────────────────

    @router.get("/categories")
    async def list_categories(_=Depends(perm)):
        return repo.list_categories()

    @router.post("/categories")
    async def create_category(body: CategoryCreate, _=Depends(perm)):
        try:
            return repo.create_category(body.name, body.prefixes)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @router.patch("/categories/{name}")
    async def update_category(name: str, body: CategoryUpdate, _=Depends(perm)):
        try:
            return repo.update_category(name, new_name=body.new_name, prefixes=body.prefixes)
        except KeyError as e:
            raise HTTPException(404, str(e))

    @router.delete("/categories/{name}")
    async def delete_category(name: str, _=Depends(perm)):
        repo.delete_category(name)
        return {"ok": True}

    @router.post("/categories/{name}/prefixes")
    async def add_prefix(name: str, body: PrefixBody, _=Depends(perm)):
        try:
            return repo.add_prefix(name, body.prefix)
        except KeyError as e:
            raise HTTPException(404, str(e))

    @router.delete("/categories/{name}/prefixes/{prefix:path}")
    async def remove_prefix(name: str, prefix: str, _=Depends(perm)):
        try:
            return repo.remove_prefix(name, prefix)
        except KeyError as e:
            raise HTTPException(404, str(e))

    # ── Assignments ──────────────────────────────────────────────────

    @router.post("/assign")
    async def assign(body: AssignBody, _=Depends(perm)):
        try:
            repo.assign(body.record_id, body.category, body.add_prefix or None)
        except KeyError as e:
            raise HTTPException(404, str(e))
        return {"ok": True}

    # ── Branches mapping ─────────────────────────────────────────────

    @router.get("/branches")
    async def list_branches(_=Depends(perm)):
        return [{"id": k, "name": v} for k, v in cfg.get_branches().items()]

    @router.post("/branches")
    async def upsert_branch(body: MappingEntry, _=Depends(perm)):
        cfg.upsert_branch(body.id, body.name)
        return {"ok": True}

    @router.delete("/branches/{bid}")
    async def delete_branch(bid: str, _=Depends(perm)):
        cfg.delete_branch(bid)
        return {"ok": True}

    # ── Payout reconciliation ─────────────────────────────────────────

    @router.get("/match-payouts")
    async def match_payouts(
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        _=Depends(perm),
    ):
        """
        For each payout in the given period, find a cash movement in Firebird
        that matches by amount and date ±1 day.
        Returns list of {payout_id, matched, move_id}.
        Explicit cash_move_id links take priority over fuzzy matching.
        """
        from datetime import timedelta
        from app.services.firebird_service import get_firebird_service, run_with_timeout
        from app.data.payout_repository import PayoutRepository

        payout_repo = PayoutRepository()
        payouts = payout_repo.list(
            from_date=str(date_from) if date_from else None,
            to_date=str(date_to) if date_to else None,
        )
        if not payouts:
            return []

        # Only match payouts paid from cash register
        cash_payouts = [p for p in payouts if "кассы" in (p.get("method") or "").lower()]
        if not cash_payouts:
            return []

        try:
            moves = await run_with_timeout(get_firebird_service().get_cash_moves, date_from=date_from, date_to=date_to)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Сузьте период и попробуйте снова.")

        # Index moves: date_str → list of (move_id, amount)
        from collections import defaultdict
        moves_by_date: dict = defaultdict(list)
        for m in moves:
            d = str(m.get("DK_DATE") or "")[:10]
            if d:
                moves_by_date[d].append((str(m.get("ID_KASSES_MOVE") or ""), float(m.get("SUMM") or 0)))

        results = []
        for p in cash_payouts:
            payout_id = p["id"]

            # Explicit link wins
            if p.get("cash_move_id"):
                results.append({"payout_id": payout_id, "matched": True, "move_id": p["cash_move_id"]})
                continue

            ts = str(p.get("timestamp") or "")[:10]
            if not ts:
                results.append({"payout_id": payout_id, "matched": False, "move_id": None})
                continue

            try:
                from datetime import date as date_cls
                payout_date = date_cls.fromisoformat(ts)
            except ValueError:
                results.append({"payout_id": payout_id, "matched": False, "move_id": None})
                continue

            payout_amount = float(p.get("amount") or 0)
            matched_id = None
            for move_id, move_amount in moves_by_date.get(ts, []):
                if abs(payout_amount - move_amount) < 0.01:
                    matched_id = move_id
                    break

            if matched_id:
                payout_repo.update(str(payout_id), {"cash_move_id": matched_id, "status": "Выплачено"})

            results.append({"payout_id": payout_id, "matched": matched_id is not None, "move_id": matched_id})

        return results

    # ── Balances ─────────────────────────────────────────────────────

    @router.get("/balances")
    async def get_cash_balances(_=Depends(perm)):
        """Current cash-on-hand per register — see
        FirebirdService.get_cash_balances for how this differs from the
        transfer-only DOC_KASSA_MOVES data the rest of this page uses."""
        from app.services.firebird_service import get_firebird_service, run_with_timeout, FIREBIRD_AVAILABLE

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")
        from app.services import fdb_cache

        try:
            return await run_with_timeout(fdb_cache.get_or_compute, "cash.balances", ())
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Попробуйте снова чуть позже.")

    @router.get("/daily-balances")
    async def get_daily_cash_balances(
        kassa_id: int,
        date_from: date,
        date_to: date,
        _=Depends(perm),
    ):
        """Остаток на начало/конец каждого дня по одной кассе — отчёт,
        с которым сотрудники сверяют фактический пересчёт кассы.

        Returns the day rows and every underlying DOCS_KASSA entry in one
        response: the detail is what turns "не сходится" into "вот эта
        проводка", and at a month's width (the page default) it's a few
        tens of KB, so splitting it into a second per-day request would
        buy nothing but a spinner on every row expansion. A full year is
        ~1300 entries / ~400 KB, which is why the service clamps the
        range to DAILY_BALANCE_MAX_DAYS and reports `clamped` back.
        """
        from app.services.firebird_service import (
            CASH_BALANCE_KASSA_IDS, get_firebird_service, run_with_timeout, FIREBIRD_AVAILABLE,
        )
        from app.services.users import get_external_code_to_name_map

        if not FIREBIRD_AVAILABLE:
            raise HTTPException(status_code=503, detail="Firebird недоступен: драйвер fdb не установлен.")
        if kassa_id not in CASH_BALANCE_KASSA_IDS:
            raise HTTPException(status_code=400, detail="Неизвестная касса.")
        from app.services import fdb_cache

        try:
            data = await run_with_timeout(
                fdb_cache.get_or_compute, "cash.daily_balances", (kassa_id, date_from, date_to),
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Сузьте период и попробуйте снова.")

        user_names = get_external_code_to_name_map()
        for entry in data.get("entries", []):
            code = entry.get("user_id") or ""
            entry["user_name"] = user_names.get(code, code or "—")
        return data

    # ── Records ──────────────────────────────────────────────────────

    @router.get("/by-id/{move_id}")
    async def get_cash_move(move_id: str, _=Depends(perm)):
        from app.services.firebird_service import get_firebird_service, run_with_timeout
        from app.services.users import get_external_code_to_name_map
        try:
            row = await run_with_timeout(get_firebird_service().get_cash_move_by_id, move_id)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Попробуйте снова чуть позже.")
        if row is None:
            raise HTTPException(404, "not found")
        user_names = get_external_code_to_name_map()
        owner_id = str(row.get("OWN_USR_ID") or "")
        row["dep_name"] = cfg.resolve_branch(row.get("DEP_SRC_ID"))
        row["user_name"] = user_names.get(owner_id, owner_id or "—")
        return row

    @router.get("/")
    async def list_cash_moves(
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        _=Depends(perm),
    ):
        from app.services.firebird_service import run_with_timeout
        from app.services import fdb_cache
        from app.data.payout_repository import PayoutRepository
        from app.services.users import get_external_code_to_name_map
        try:
            # Positional args, matching the warmer's cache key — the
            # keyword form this used to pass would hash to a different key
            # and never hit.
            rows = await run_with_timeout(fdb_cache.get_or_compute, "cash.moves", (date_from, date_to))
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Запрос выполняется слишком долго. Сузьте период и попробуйте снова.")
        assignments = repo.get_assignments()
        payout_repo = PayoutRepository()
        linked_ids = payout_repo.linked_cash_move_ids()
        linked_payouts = payout_repo.linked_payouts_by_move_id()
        user_names = get_external_code_to_name_map()
        for r in rows:
            rid = str(r.get("ID_KASSES_MOVE") or "")
            owner_id = str(r.get("OWN_USR_ID") or "")
            r["dep_name"] = cfg.resolve_branch(r.get("DEP_SRC_ID"))
            r["user_name"] = user_names.get(owner_id, owner_id or "—")
            category = repo.resolve_category(rid, r.get("BASIS"))
            r["category"] = category
            r["prefix_ok"] = category is not None
            r["manually_assigned"] = rid in assignments
            r["has_payout"] = rid in linked_ids
            r["linked_payout"] = linked_payouts.get(rid)
        return rows

    return router
