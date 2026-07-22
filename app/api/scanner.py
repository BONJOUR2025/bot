"""API for parsing 3D foot-scan (.scm) files into human-readable data."""
from __future__ import annotations

import asyncio
import base64

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.services.access_control_service import ResolvedUser
from app.services.scm_parser_service import parse_scm

from .dependencies import require_permission

SCANNER_PERMISSION = "3d-scanner"


def create_scanner_router() -> APIRouter:
    router = APIRouter(prefix="/scanner", tags=["Scanner"])

    @router.post("/parse")
    async def parse(
        file: UploadFile = File(...),
        current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION)),
    ):
        if not file.filename or not file.filename.lower().endswith(".scm"):
            raise HTTPException(status_code=400, detail="expected_scm_file")
        raw = await file.read()
        try:
            # CPU-bound (numpy scan over the whole file + PNG encoding) —
            # off the event loop so a big/slow parse doesn't stall the API
            # for every other user, same lesson as firebird_service's
            # TTLCache / payout_service's cash-move lookup.
            result = await asyncio.to_thread(parse_scm, raw)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"parse_failed: {exc}")

        feet_out = []
        for foot in result["feet"]:
            views_b64 = {
                name: "data:image/png;base64," + base64.b64encode(png).decode("ascii")
                for name, png in foot["views_png"].items()
            }
            feet_out.append({
                "side": foot["side"],
                "point_count": foot["point_count"],
                "length_mm": foot["length_mm"],
                "width_mm": foot["width_mm"],
                "height_mm": foot["height_mm"],
                "ball_girth_mm": foot["ball_girth_mm"],
                "instep_girth_mm": foot.get("instep_girth_mm"),
                "views": views_b64,
            })

        return {
            "metadata": result["metadata"],
            "feet": feet_out,
            "file_size": result["file_size"],
        }

    return router
