"""API for the shoe-last article/model number registry (колодка №4977, ...) --
separate from individual last scans (see app/api/lasts.py), so the "add a
last" form can offer a dropdown of known numbers instead of free text."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException

from app.data.last_article_repository import LastArticleRepository
from app.data.last_repository import LastRepository
from app.services.access_control_service import ResolvedUser

from .dependencies import require_permission
from .scanner import SCANNER_PERMISSION


def create_last_articles_router() -> APIRouter:
    router = APIRouter(prefix="/last-articles", tags=["Last articles"])
    repo = LastArticleRepository()
    lasts_repo = LastRepository()

    @router.get("")
    async def list_articles(current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION))):
        return {"articles": repo.list()}

    @router.post("")
    async def create_article(
        code: str = Form(...),
        name: str = Form(""),
        note: str = Form(""),
        current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION)),
    ):
        code = code.strip()
        if not code:
            raise HTTPException(status_code=400, detail="code_required")
        if repo.get_by_code(code):
            raise HTTPException(status_code=409, detail="code_already_exists")
        return repo.create({"code": code, "name": name, "note": note})

    @router.patch("/{article_id}")
    async def update_article(
        article_id: str,
        code: str = Form(...),
        name: str = Form(""),
        note: str = Form(""),
        current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION)),
    ):
        existing = repo.get(article_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="not_found")
        code = code.strip()
        if not code:
            raise HTTPException(status_code=400, detail="code_required")
        clash = repo.get_by_code(code)
        if clash and clash["id"] != article_id:
            raise HTTPException(status_code=409, detail="code_already_exists")
        old_code = existing["code"]
        updated = repo.update(article_id, {"code": code, "name": name, "note": note})
        lasts_repo.rename_article(old_code, code)
        return updated

    @router.delete("/{article_id}")
    async def delete_article(article_id: str, current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION))):
        record = repo.delete(article_id)
        if record is None:
            raise HTTPException(status_code=404, detail="not_found")
        return {"ok": True}

    return router
