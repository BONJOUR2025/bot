"""End-to-end fit analysis -- the §21 pipeline, reported in the §24.2 shape.

Runs the stages the research report insists must stay separate (§26.10 lists
"смешивание ориентации, регистрации, позы и fit analysis" among the things to
remove), each handing back its own object, confidence and warnings:

    mesh QA -> landmarks -> last working orientation -> heel-fixed registration
    -> cavity estimate -> curvilinear sections -> clearance -> uncertainty

This is `engine="fit_v3"`. It runs alongside the existing `hybrid_v2` rather
than replacing it: hybrid_v2 is what the admin panel reads today, and swapping
the engine underneath a live UI is a separate, deliberate decision. §20.5
requires every report to say which mode produced it, so `analysis_mode` and
`limitations` travel with the result.

Deliberately NOT claimed here (§31.3): a single true foot shape inside the
shoe, pressure, or a guaranteed comfort verdict. With only two STLs the output
is a probabilistic geometric model, and the report says so.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh

from app.services.curvilinear_sections import build_centerline, sections_along
from app.services.fit_clearance import ClearanceReport, compute_clearance
from app.services.foot_landmarks import detect_foot_landmarks
from app.services.heel_fixed_registration import register_foot_to_last
from app.services.last_registration_service import initial_align
from app.services.last_working_orientation import estimate_working_orientation
from app.services.mesh3d_service import mesh_quality_report, repair_small_holes
from app.services.shoe_cavity import build_cavity

SECTION_FRACTIONS = (0.45, 0.50, 0.55, 0.67, 0.75, 0.80)

# §17.2 fit classes, restricted to the ones this evidence can actually support.
FIT_GOOD = "FIT_GOOD"
FIT_LOCAL_TIGHTNESS = "FIT_LOCAL_TIGHTNESS"
FIT_LOCAL_LOOSENESS = "FIT_LOCAL_LOOSENESS"
FIT_REQUIRES_LAST_MODIFICATION = "FIT_REQUIRES_LAST_MODIFICATION"
FIT_INDETERMINATE = "FIT_INDETERMINATE"

_MANY_TIGHT_ZONES = 3


@dataclass
class FitReport:
    fit_class: str
    confidence: float
    analysis_mode: str
    landmarks: dict
    registration: dict
    working_orientation: dict
    cavity: dict
    sections: list[dict]
    clearance: dict
    quality: dict
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "engine": "fit_v3",
            "fit_class": self.fit_class,
            "confidence": round(self.confidence, 3),
            "analysis_mode": self.analysis_mode,
            "landmarks": self.landmarks,
            "registration": self.registration,
            "working_orientation": self.working_orientation,
            "cavity": self.cavity,
            "sections": self.sections,
            "clearance": self.clearance,
            "quality": self.quality,
            "limitations": list(self.limitations),
        }


def _classify(clearance: ClearanceReport) -> str:
    """§17.1: no winner-takes-all. The class summarises the zone profile, and
    the per-zone detail stays in the report for the reader to disagree with."""
    if not clearance.zones:
        return FIT_INDETERMINATE
    tight = [z for z in clearance.zones if z.classification == "LOCAL_TIGHTNESS"]
    loose = [z for z in clearance.zones if z.classification == "LOCAL_LOOSENESS"]
    if len(tight) >= _MANY_TIGHT_ZONES:
        # Tightness spread across most of the foot is not a local problem to
        # be eased -- it is the wrong last (§15.3).
        return FIT_REQUIRES_LAST_MODIFICATION
    if tight:
        return FIT_LOCAL_TIGHTNESS
    if loose:
        return FIT_LOCAL_LOOSENESS
    return FIT_GOOD


def analyze_fit(
    foot_mesh: trimesh.Trimesh,
    last_mesh: trimesh.Trimesh,
    foot_side: str | None = None,
    last_side: str | None = None,
    construction: dict | None = None,
    analysis_mode: str = "STATIC_GEOMETRY",
) -> FitReport:
    """§21 pipeline. `analysis_mode="STATIC_GEOMETRY"` compares the foot as
    scanned (§20.1) -- no pose is inferred, which keeps the pose uncertainty
    out of the budget entirely."""
    limitations: list[str] = []

    # 1-4. mesh QA, on copies -- the caller's meshes are never touched (§19.1).
    foot_repaired, foot_fixed = repair_small_holes(foot_mesh)
    last_repaired, last_fixed = repair_small_holes(last_mesh)
    foot_quality = mesh_quality_report(foot_repaired)
    last_quality = mesh_quality_report(last_repaired)
    if not foot_quality.valid_for_signed_distance:
        limitations.append("foot mesh is not a closed volume")
    if foot_fixed or last_fixed:
        limitations.append("small holes were repaired before analysis")

    foot_aligned = initial_align(foot_repaired)
    last_aligned = initial_align(last_repaired)

    # 5-8. landmarks, independently and with confidence
    foot_landmarks = detect_foot_landmarks(foot_aligned, side=foot_side)
    if foot_landmarks.confidence < 0.3:
        # §21.1 gate: a weak landmark set must lower the whole result, not be
        # quietly relied upon.
        limitations.append("low landmark confidence -- geometry-only reading")

    # 9. last working orientation (effective heel elevation, not a rear vertex)
    orientation = estimate_working_orientation(last_aligned)

    # 10-11. heel-fixed rigid registration
    registration, foot_registered, last_used = register_foot_to_last(
        foot_aligned, last_aligned, foot_side, last_side, foot_landmarks=foot_landmarks,
    )
    if not registration.within_tolerance:
        limitations.append("heel could not be pinned within the §9.5 tolerance")

    # 12. curvilinear sections, square to the foot's own centreline
    centerline = build_centerline(foot_registered)
    sections = [s.as_dict() for s in sections_along(foot_registered, SECTION_FRACTIONS, centerline)] \
        if centerline is not None else []
    if not sections:
        limitations.append("cross-sections unavailable")

    # 13. estimated shoe cavity
    cavity = build_cavity(last_used, construction)

    # 14-17. clearance against the cavity, with the uncertainty budget
    clearance = compute_clearance(
        foot_registered, cavity.mesh, mesh_quality_report(cavity.mesh),
        cavity_mode=cavity.cavity_mode,
        analysis_mode=analysis_mode,
        pose_applied=False,
    )

    # 22-23. classification, with confidence limited by its weakest input
    confidence = min(
        registration.confidence,
        max(foot_landmarks.confidence, 0.05),
        max(orientation.orientation_confidence, 0.05) if orientation.heel_support else 0.5,
    )
    limitations.extend(clearance.limitations)
    limitations.append(
        "probabilistic geometric model from two STLs -- not a measured foot shape inside a shoe"
    )

    return FitReport(
        fit_class=_classify(clearance),
        confidence=confidence,
        analysis_mode=analysis_mode,
        landmarks=foot_landmarks.as_dict(),
        registration=registration.as_dict(),
        working_orientation=orientation.as_dict(),
        cavity=cavity.as_dict(),
        sections=sections,
        clearance=clearance.as_dict(),
        quality={"foot": foot_quality.as_dict(), "cavity": last_quality.as_dict()},
        limitations=limitations,
    )
