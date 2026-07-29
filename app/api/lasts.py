"""API for the shoe-last (колодка) library: upload/list/delete lasts, and
match a foot scan against one or all lasts, section-by-section, explaining fit."""
from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.data.last_repository import LastRepository
from app.services.access_control_service import ResolvedUser
from app.services.fit_pipeline import analyze_fit
from app.services.last_fit_hybrid_service import combine_bilateral, compare_hybrid
from app.services.mesh_visualization_service import build_visualization_payload
from app.services.last_fit_service import compare_profiles
from app.services.stl_parser_service import load_stl_mesh, parse_stl

from .dependencies import require_permission
from .scanner import SCANNER_PERMISSION

UPLOAD_DIR = Path("static/uploads/lasts")
SCAN_EXTENSIONS = (".stl",)


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
        # A production last exists as a whole graded family: one model number
        # (e.g. 4977) issued in several sizes and several width grades. article
        # names the family, size and fullness pick the individual last inside
        # it, so the library can be laid out as a size x fullness grid.
        article: str = Form(""),
        size: str = Form(""),
        fullness: str = Form(""),
        model: str = Form(""),
        material: str = Form(""),
        note: str = Form(""),
        side: str | None = Form(None),  # "left"/"right" override — used when
                                         # the scan's own metadata doesn't say
                                         # (some scans just don't have the
                                         # "левая/правая колодка" text), since
                                         # an unknown side silently disables
                                         # mirroring for whichever foot needs it
        heel_height_mm: float | None = Form(None),  # hybrid_v2 pose model overrides —
        toe_spring_mm: float | None = Form(None),   # optional manual values that force
                                                     # last_pose_service.apply_pose's simple
                                                     # whole-foot lift instead of the default
                                                     # automatic per-last measurement +
                                                     # local-frame deformation (see
                                                     # foot_pose_deformation.resolve_foot_pose)
        current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION)),
    ):
        ext = Path(file.filename or "").suffix.lower()
        if ext not in SCAN_EXTENSIONS:
            raise HTTPException(status_code=400, detail="expected_stl_file")
        if side not in (None, "", "left", "right"):
            raise HTTPException(status_code=400, detail="invalid_side")
        raw = await file.read()
        try:
            block = await asyncio.to_thread(parse_stl, raw)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"parse_failed: {exc}")

        record = repo.create({
            "article": article, "size": size, "fullness": fullness, "model": model,
            "material": material, "note": note,
            "engine": "slice_v1",  # which pipeline computed "profile" below
            # .stl has no side hint in the file itself (unlike .scm's
            # "левая/правая колодка" header text) — the form field is the
            # only source there.
            "side": (side or None) or block.get("side"),
            "heel_height_mm": heel_height_mm,
            "toe_spring_mm": toe_spring_mm,
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

    @router.patch("/{last_id}")
    async def update_last(
        last_id: str,
        # Metadata only -- fixing a typo'd size/fullness/note on an already
        # scanned last shouldn't require re-uploading the .stl. Re-scanning
        # (a new file, and everything stl_parser_service measures from it)
        # is a separate action: delete and re-add.
        article: str = Form(""),
        size: str = Form(""),
        fullness: str = Form(""),
        model: str = Form(""),
        material: str = Form(""),
        note: str = Form(""),
        side: str | None = Form(None),
        heel_height_mm: float | None = Form(None),
        toe_spring_mm: float | None = Form(None),
        current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION)),
    ):
        if side not in (None, "", "left", "right"):
            raise HTTPException(status_code=400, detail="invalid_side")
        if repo.get(last_id) is None:
            raise HTTPException(status_code=404, detail="not_found")
        record = repo.update(last_id, {
            "article": article, "size": size, "fullness": fullness, "model": model,
            "material": material, "note": note, "side": side or None,
            "heel_height_mm": heel_height_mm, "toe_spring_mm": toe_spring_mm,
        })
        return _last_summary(record)

    @router.delete("/{last_id}")
    async def delete_last(last_id: str, current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION))):
        existing = repo.get(last_id)
        record = repo.delete(last_id)
        if record is None:
            raise HTTPException(status_code=404, detail="not_found")
        ext = Path(existing["scan_file_url"]).suffix if existing and existing.get("scan_file_url") else ".stl"
        (UPLOAD_DIR / f"{last_id}{ext}").unlink(missing_ok=True)
        return {"ok": True}

    @router.post("/match")
    async def match_foot(
        file: UploadFile | None = File(None),
        file_left: UploadFile | None = File(None),
        file_right: UploadFile | None = File(None),
        last_id: str | None = Form(None),
        swap_sides: bool = Form(False),
        # "fit_v3" (default) is the research-report pipeline (fit_pipeline.py):
        # it attaches a per-foot `fit_result` with the verdict, the plain
        # language explanation and the footprint overlay. "slice_v1" and
        # "hybrid_v2" are the older engines, kept for comparison.
        engine: str = Form("fit_v3"),
        # Heavy (base64 GLB meshes + problem-patch submeshes) — only built
        # when explicitly asked and only alongside engine=hybrid_v2, since
        # slice_v1 has no mesh to visualize with.
        include_geometry: bool = Form(False),
        current: ResolvedUser = Depends(require_permission(SCANNER_PERMISSION)),
    ):
        # The scanner's .stl export is one foot per file, so a full pair needs
        # two uploads, each tagged with its side explicitly (an .stl carries no
        # side hint of its own).
        foot_raw_by_side: dict[str, bytes] = {}
        if file_left is not None or file_right is not None:
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
                foot_raw_by_side[side] = raw
        else:
            raise HTTPException(status_code=400, detail="expected_stl_file")

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

        response_engine = "slice_v1"

        if engine == "fit_v3" and foot_raw_by_side:
            # The §21 pipeline (fit_pipeline.py). Kept beside hybrid_v2 rather
            # than replacing it: the admin panel reads hybrid_v2's shape today,
            # and swapping the engine underneath a live UI is its own decision.
            targets_by_id = {t["id"]: t for t in targets}

            def _run_fit_v3():
                for match in matches:
                    last = targets_by_id[match["last"]["id"]]
                    url = last.get("scan_file_url") or ""
                    if not url.lower().endswith(".stl"):
                        continue
                    last_path = Path(url.lstrip("/"))
                    if not last_path.exists():
                        continue
                    last_mesh = load_stl_mesh(last_path.read_bytes())
                    for pf in match["per_foot"]:
                        raw = foot_raw_by_side.get(pf["foot_side"])
                        if raw is None:
                            continue
                        try:
                            foot_mesh = load_stl_mesh(raw)
                            fit = analyze_fit(
                                foot_mesh, last_mesh,
                                pf["foot_side"], last.get("side"),
                            ).as_dict()
                            if include_geometry:
                                try:
                                    fit["visualization"] = build_visualization_payload(
                                        foot_mesh, pf["foot_side"], last_mesh,
                                        last.get("side"),
                                        # fit_v3 marks problem zones itself; the
                                        # scene only needs the heatmap and the
                                        # meshes, so no pattern patches are fed in.
                                        {"patterns": [], "critical_sections": [], "zones": {}},
                                    )
                                except Exception as exc:
                                    fit["visualization_error"] = str(exc)
                            pf["fit_result"] = fit
                        except Exception as exc:
                            pf["fit_result"] = {"engine": "fit_v3", "error": str(exc)}

            await asyncio.to_thread(_run_fit_v3)

            # Re-sort on what the panel actually shows. The ordering above
            # comes from slice_v1's own overlap score, which has nothing to do
            # with the fit_v3 verdict rendered on each card -- so the list read
            # as unranked: a last headed "подходит" sat below two headed "не
            # тот размер". Rank by the displayed class, then by how far outside
            # acceptable its worst reading sits. Lasts fit_v3 could not judge
            # keep their old position at the end rather than jumping the queue.
            def _rank(match):
                results = [pf.get("fit_result") or {} for pf in match["per_foot"]]
                usable = [r for r in results if "class_order" in r]
                if not usable:
                    return (99, 0.0)
                return (max(r["class_order"] for r in usable),
                        max(r.get("worst_deviation_mm") or 0.0 for r in usable))

            matches.sort(key=_rank)

            # Rank ties. Ordering by a millimetre figure implies the order
            # means something, and between the top two lasts of one family it
            # did not: 5.0mm against 5.8mm, both driven by the same length
            # allowance, against a measurement budget of 2.7mm. Presented as a
            # list that reads 1st and 2nd, that invites "so 7 fits me better
            # than 6?" -- and the honest answer is no, they are the same
            # reading. Entries sharing a class whose deviations differ by less
            # than the uncertainty carry the same tier, so the panel can say so
            # instead of implying a winner.
            def _sigma(match):
                for pf in match["per_foot"]:
                    unc = ((pf.get("fit_result") or {}).get("clearance") or {}).get("uncertainty")
                    if unc and unc.get("total_sigma_mm"):
                        return float(unc["total_sigma_mm"])
                return 1.0

            tier = 0
            anchor = None
            for i, match in enumerate(matches):
                cls, dev = _rank(match)
                if anchor is None or cls != anchor[0] or abs(dev - anchor[1]) >= _sigma(match):
                    tier = i + 1
                    anchor = (cls, dev)
                match["tier"] = tier

            response_engine = "fit_v3"

        if engine == "hybrid_v2" and foot_raw_by_side:
            targets_by_id = {t["id"]: t for t in targets}

            def _run_hybrid():
                for match in matches:
                    last = targets_by_id[match["last"]["id"]]
                    url = last.get("scan_file_url") or ""
                    if not url.lower().endswith(".stl"):
                        continue  # .scm last has no mesh to compare a surface against
                    last_path = Path(url.lstrip("/"))
                    if not last_path.exists():
                        continue
                    cavity_mesh = load_stl_mesh(last_path.read_bytes())
                    for pf in match["per_foot"]:
                        raw = foot_raw_by_side.get(pf["foot_side"])
                        if raw is None:
                            continue
                        foot_mesh = load_stl_mesh(raw)
                        try:
                            pf["surface_result"] = compare_hybrid(
                                foot_mesh, pf["foot_side"], cavity_mesh, last.get("side"),
                                heel_height_mm=last.get("heel_height_mm"),
                                toe_spring_mm=last.get("toe_spring_mm"),
                            )
                        except Exception as exc:
                            pf["surface_result"] = {"engine": "hybrid_v2", "error": str(exc)}
                            continue

                        if include_geometry:
                            try:
                                pf["surface_result"]["visualization"] = build_visualization_payload(
                                    foot_mesh, pf["foot_side"], cavity_mesh, last.get("side"),
                                    pf["surface_result"],
                                    heel_height_mm=last.get("heel_height_mm"),
                                    toe_spring_mm=last.get("toe_spring_mm"),
                                )
                            except Exception as exc:
                                pf["surface_result"]["visualization_error"] = str(exc)

                    # A last is chosen for a *pair* of feet — if both sides
                    # got a surface_result against this same last, report
                    # which one should actually govern a sizing/fullness
                    # decision (see last_fit_hybrid_service.combine_bilateral).
                    by_side = {pf["foot_side"]: pf.get("surface_result") for pf in match["per_foot"]}
                    bilateral = combine_bilateral(by_side.get("left"), by_side.get("right"))
                    if bilateral is not None:
                        match["bilateral"] = bilateral

            await asyncio.to_thread(_run_hybrid)
            response_engine = "hybrid_v2"

        # "engine" marks which comparison pipeline produced this response —
        # slice_v1 (the cross-sectional pipeline that's been here since the
        # start) always runs and is never altered by requesting hybrid_v2;
        # hybrid_v2 only adds a "surface_result" per per_foot entry above.
        # Frozen as of the slice_v1 → hybrid_v2 migration: legacy_slice_v1
        # response shape/numbers must not silently change (see
        # tests/test_last_fit_regression.py).
        return {"engine": response_engine, "feet": feet_out, "matches": matches}

    return router
