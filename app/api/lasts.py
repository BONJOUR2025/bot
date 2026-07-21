"""API for the shoe-last (колодка) library: upload/list/delete lasts, and
match a foot scan against one or all lasts in the library."""
from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.data.last_repository import LastRepository
from app.services.access_control_service import ResolvedUser
from app.services.last_fit_service import evaluate_fit
from app.services.scm_parser_service import parse_scm

from .dependencies import require_permission
from .scanner import SCANNER_PERMISSION

UPLOAD_DIR = Path("static/uploads/lasts")


def _blocks_from_parsed(result: dict) -> list[dict]:
    return [
        {
            "side": foot["side"],
            "point_count": foot["point_count"],
            "length_mm": foot["length_mm"],
            "width_mm": foot["width_mm"],
            "height_mm": foot["height_mm"],
            "ball_girth_mm": foot["ball_girth_mm"],
        }
        for foot in result["feet"]
    ]


def _pick_last_block(last: dict, foot_side: str | None) -> dict | None:
    blocks = last["blocks"]
    if not blocks:
        return None
    if foot_side:
        for b in blocks:
            if b["side"] == foot_side:
                return b
    return blocks[0]


def create_lasts_router() -> APIRouter:
    router = APIRouter(prefix="/lasts", tags=["Lasts"])
    repo = LastRepository()

    @router.get("")
    async def list_lasts(current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION))):
        return {"lasts": repo.list()}

    @router.post("")
    async def create_last(
        file: UploadFile = File(...),
        article: str = Form(""),
        size: str = Form(""),
        model: str = Form(""),
        material: str = Form(""),
        note: str = Form(""),
        current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION)),
    ):
        if not file.filename or not file.filename.lower().endswith(".scm"):
            raise HTTPException(status_code=400, detail="expected_scm_file")
        raw = await file.read()
        try:
            result = await asyncio.to_thread(parse_scm, raw)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"parse_failed: {exc}")

        blocks = _blocks_from_parsed(result)
        if not blocks:
            raise HTTPException(status_code=422, detail="no_last_geometry_found")

        record = repo.create({
            "article": article, "size": size, "model": model,
            "material": material, "note": note,
            "blocks": blocks,
        })
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        dest = UPLOAD_DIR / f"{record['id']}.scm"
        dest.write_bytes(raw)
        url = f"/static/uploads/lasts/{record['id']}.scm"
        repo.set_scan_file_url(record["id"], url)
        record["scan_file_url"] = url
        return record

    @router.delete("/{last_id}")
    async def delete_last(last_id: str, current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION))):
        record = repo.delete(last_id)
        if record is None:
            raise HTTPException(status_code=404, detail="not_found")
        scan_path = UPLOAD_DIR / f"{last_id}.scm"
        scan_path.unlink(missing_ok=True)
        return {"ok": True}

    @router.post("/match")
    async def match_foot(
        file: UploadFile = File(...),
        last_id: str | None = Form(None),
        current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION)),
    ):
        if not file.filename or not file.filename.lower().endswith(".scm"):
            raise HTTPException(status_code=400, detail="expected_scm_file")
        raw = await file.read()
        try:
            result = await asyncio.to_thread(parse_scm, raw)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"parse_failed: {exc}")

        feet = result["feet"]
        if not feet:
            raise HTTPException(status_code=422, detail="no_foot_geometry_found")

        feet_out = []
        for foot in feet:
            views_b64 = {
                name: "data:image/png;base64," + base64.b64encode(png).decode("ascii")
                for name, png in foot["views_png"].items()
            }
            # whitelist fields (not a blind copy) — byte_range holds numpy
            # int64s from the block-finding scan, which FastAPI/pydantic
            # can't serialize.
            feet_out.append({
                "side": foot["side"],
                "point_count": foot["point_count"],
                "length_mm": foot["length_mm"],
                "width_mm": foot["width_mm"],
                "height_mm": foot["height_mm"],
                "ball_girth_mm": foot["ball_girth_mm"],
                "views": views_b64,
            })

        if last_id is not None:
            last = repo.get(last_id)
            if last is None:
                raise HTTPException(status_code=404, detail="last_not_found")
            targets = [last]
        else:
            targets = repo.list()

        matches = []
        for last in targets:
            per_foot = []
            for foot in feet:
                last_block = _pick_last_block(last, foot["side"])
                if last_block is None:
                    continue
                per_foot.append({
                    "foot_side": foot["side"],
                    "fit": evaluate_fit(foot, last_block),
                })
            if not per_foot:
                continue
            worst_rank = max(
                {"good": 0, "ok": 1, "loose": 2, "not_fit": 3}[pf["fit"]["overall"]]
                for pf in per_foot
            )
            score = sum(
                abs(m["delta_mm"]) for pf in per_foot for m in pf["fit"]["metrics"]
            )
            matches.append({
                "last": last,
                "per_foot": per_foot,
                "_worst_rank": worst_rank,
                "_score": score,
            })
        matches.sort(key=lambda m: (m["_worst_rank"], m["_score"]))
        for m in matches:
            del m["_worst_rank"]
            del m["_score"]

        return {"feet": feet_out, "matches": matches}

    return router
