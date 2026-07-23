"""API for the shoe-last (колодка) library: upload/list/delete lasts, and
match a foot scan against one or all lasts, section-by-section, explaining fit."""
from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.data.last_repository import LastRepository
from app.services.access_control_service import ResolvedUser
from app.services.last_fit_service import compare_profiles
from app.services.scm_parser_service import parse_scm
from app.services.stl_parser_service import parse_stl

from .dependencies import require_permission
from .scanner import SCANNER_PERMISSION

UPLOAD_DIR = Path("static/uploads/lasts")
SCAN_EXTENSIONS = (".scm", ".stl")


def _foot_profile(foot: dict) -> dict:
    """Merge the per-section profile with the named girths into one dict, the
    shape last_fit_service.compare_profiles expects."""
    return {
        **foot["profile"],
        "ball_girth_mm": foot.get("ball_girth_mm"),
        "instep_girth_mm": foot.get("instep_girth_mm"),
        "ball_line_mm": foot.get("ball_line_mm"),
    }


def _last_summary(last: dict) -> dict:
    """Last record without the bulky profile array — for list/match responses."""
    return {k: v for k, v in last.items() if k != "profile"}


def create_lasts_router() -> APIRouter:
    router = APIRouter(prefix="/lasts", tags=["Lasts"])
    repo = LastRepository()

    @router.get("")
    async def list_lasts(current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION))):
        return {"lasts": [_last_summary(l) for l in repo.list()]}

    @router.post("")
    async def create_last(
        file: UploadFile = File(...),
        article: str = Form(""),
        size: str = Form(""),
        model: str = Form(""),
        material: str = Form(""),
        note: str = Form(""),
        side: str | None = Form(None),  # "left"/"right" override — used when
                                         # the scan's own metadata doesn't say
                                         # (some scans just don't have the
                                         # "левая/правая колодка" text), since
                                         # an unknown side silently disables
                                         # mirroring for whichever foot needs it
        current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION)),
    ):
        ext = Path(file.filename or "").suffix.lower()
        if ext not in SCAN_EXTENSIONS:
            raise HTTPException(status_code=400, detail="expected_scm_or_stl_file")
        if side not in (None, "", "left", "right"):
            raise HTTPException(status_code=400, detail="invalid_side")
        raw = await file.read()
        try:
            if ext == ".scm":
                result = await asyncio.to_thread(parse_scm, raw)
                feet = result["feet"]
                if not feet:
                    raise HTTPException(status_code=422, detail="no_last_geometry_found")
                # A last is one shape (both sides are mirror-identical) — take one block.
                block = feet[0]
            else:
                block = await asyncio.to_thread(parse_stl, raw)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"parse_failed: {exc}")

        record = repo.create({
            "article": article, "size": size, "model": model,
            "material": material, "note": note,
            # .stl has no side hint in the file itself (unlike .scm's
            # "левая/правая колодка" header text) — the form field is the
            # only source there.
            "side": (side or None) or block.get("side"),
            "length_mm": block["length_mm"],
            "width_mm": block["width_mm"],
            "height_mm": block["height_mm"],
            "ball_girth_mm": block["ball_girth_mm"],
            "instep_girth_mm": block.get("instep_girth_mm"),
            "ball_line_mm": block.get("ball_line_mm"),
            "profile": block["profile"],
        })
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        (UPLOAD_DIR / f"{record['id']}{ext}").write_bytes(raw)
        url = f"/static/uploads/lasts/{record['id']}{ext}"
        repo.set_scan_file_url(record["id"], url)
        record["scan_file_url"] = url
        return _last_summary(record)

    @router.delete("/{last_id}")
    async def delete_last(last_id: str, current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION))):
        existing = repo.get(last_id)
        record = repo.delete(last_id)
        if record is None:
            raise HTTPException(status_code=404, detail="not_found")
        ext = Path(existing["scan_file_url"]).suffix if existing and existing.get("scan_file_url") else ".scm"
        (UPLOAD_DIR / f"{last_id}{ext}").unlink(missing_ok=True)
        return {"ok": True}

    @router.post("/match")
    async def match_foot(
        file: UploadFile | None = File(None),
        file_left: UploadFile | None = File(None),
        file_right: UploadFile | None = File(None),
        last_id: str | None = Form(None),
        swap_sides: bool = Form(False),
        current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION)),
    ):
        # Two upload shapes: one .scm file with both feet inside (legacy), or
        # one/two .stl files — the scanner's .stl export is one foot per
        # file, so a full pair needs two separate uploads, each tagged with
        # its side explicitly (an .stl has no side hint to read, unlike
        # .scm's header text).
        if file is not None:
            if not file.filename or not file.filename.lower().endswith(".scm"):
                raise HTTPException(status_code=400, detail="expected_scm_file")
            raw = await file.read()
            try:
                result = await asyncio.to_thread(parse_scm, raw)
            except Exception as exc:
                raise HTTPException(status_code=422, detail=f"parse_failed: {exc}")
            feet = result["feet"]
        elif file_left is not None or file_right is not None:
            feet = []
            for side, upload in (("left", file_left), ("right", file_right)):
                if upload is None:
                    continue
                if not upload.filename or not upload.filename.lower().endswith(".stl"):
                    raise HTTPException(status_code=400, detail="expected_stl_file")
                raw = await upload.read()
                try:
                    block = await asyncio.to_thread(parse_stl, raw)
                except Exception as exc:
                    raise HTTPException(status_code=422, detail=f"parse_failed: {exc}")
                block["side"] = side
                feet.append(block)
        else:
            raise HTTPException(status_code=400, detail="expected_scm_or_stl_file")

        if not feet:
            raise HTTPException(status_code=422, detail="no_foot_geometry_found")
        if swap_sides and len(feet) == 2:
            # The two blocks' geometry is unchanged — only which one is
            # "left" vs "right" was guessed wrong (byte order isn't a
            # guarantee, just the pattern seen on every reference scan so
            # far). Swapping the label is the whole fix: it corrects both
            # the displayed side and which last gets mirrored against which
            # foot in the comparison below.
            feet[0]["side"], feet[1]["side"] = feet[1]["side"], feet[0]["side"]

        feet_out = []
        for foot in feet:
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

        if last_id is not None:
            last = repo.get(last_id)
            if last is None:
                raise HTTPException(status_code=404, detail="last_not_found")
            targets = [last]
        else:
            targets = repo.list()

        last_profiles = {
            l["id"]: {**l["profile"], "ball_girth_mm": l.get("ball_girth_mm"),
                      "instep_girth_mm": l.get("instep_girth_mm"),
                      "ball_line_mm": l.get("ball_line_mm"), "length_mm": l["length_mm"]}
            for l in targets
        }

        # Comparison is CPU-bound (section resampling + 2 matplotlib renders per
        # foot per last) — keep it off the event loop.
        def _run_matches():
            out = []
            for last in targets:
                lp = last_profiles[last["id"]]
                per_foot = []
                for foot in feet:
                    fit = compare_profiles(
                        _foot_profile(foot), lp,
                        foot_side=foot.get("side"), last_side=last.get("side"),
                    )
                    per_foot.append({"foot_side": foot["side"], "fit": fit})
                rank = {"good": 0, "ok": 1, "uncertain": 1, "loose": 2, "not_fit": 3}
                worst = max(rank[pf["fit"]["overall"]] for pf in per_foot)
                score = -min(pf["fit"]["overlap_pct"] for pf in per_foot)
                out.append({"last": _last_summary(last), "per_foot": per_foot,
                            "_worst": worst, "_score": score})
            out.sort(key=lambda m: (m["_worst"], m["_score"]))
            for m in out:
                del m["_worst"]; del m["_score"]
            return out

        matches = await asyncio.to_thread(_run_matches)
        return {"feet": feet_out, "matches": matches}

    return router
