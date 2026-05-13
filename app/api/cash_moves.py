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
            "users": cfg.get_users(),
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

    # ── Users mapping ────────────────────────────────────────────────

    @router.get("/users")
    async def list_users(_=Depends(perm)):
        return [{"id": k, "name": v} for k, v in cfg.get_users().items()]

    @router.post("/users")
    async def upsert_user(body: MappingEntry, _=Depends(perm)):
        cfg.upsert_user(body.id, body.name)
        return {"ok": True}

    @router.delete("/users/{uid}")
    async def delete_user(uid: str, _=Depends(perm)):
        cfg.delete_user(uid)
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

    # ── Records ──────────────────────────────────────────────────────

    @router.get("/")
    async def list_cash_moves(
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        _=Depends(perm),
    ):
        from app.services.firebird_service import get_firebird_service
        rows = get_firebird_service().get_cash_moves(date_from=date_from, date_to=date_to)
        assignments = repo.get_assignments()
        for r in rows:
            rid = str(r.get("ID_KASSES_MOVE") or "")
            r["dep_name"] = cfg.resolve_branch(r.get("DEP_SRC_ID"))
            r["user_name"] = cfg.resolve_user(r.get("OWN_USR_ID"))
            category = repo.resolve_category(rid, r.get("BASIS"))
            r["category"] = category
            r["prefix_ok"] = category is not None
            r["manually_assigned"] = rid in assignments
        return rows

    return router
