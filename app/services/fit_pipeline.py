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
from app.services.fit_explanation import explain
from app.services.fit_footprint import render_footprint_overlay
from app.services.fit_size_match import evaluate_size_match
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
# §17.2/§15: the last is the wrong size or proportion for this foot, so no
# amount of easing or a different fullness will help.
FIT_STRUCTURALLY_INCOMPATIBLE = "FIT_STRUCTURALLY_INCOMPATIBLE"
# Length and ball-line placement passed fit_size_match -- the last is the
# right size -- but tightness (or looseness) is spread broadly rather than
# local, which on a correctly-sized last is what a wrong width grade looks
# like. Distinct from FIT_REQUIRES_LAST_MODIFICATION: that name covers a last
# that is wrong outright; this one means "same model and length, next width
# grade up/down" -- a real, common, and much cheaper fix on a graded family
# (see the size x fullness library grid).
FIT_REQUIRES_DIFFERENT_FULLNESS = "FIT_REQUIRES_DIFFERENT_FULLNESS"

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
    size_match: dict
    clearance: dict
    quality: dict
    fullness_direction: str | None = None
    fullness_mm: float | None = None
    explanation: dict = field(default_factory=dict)
    footprint_png_base64: str | None = None
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
            "size_match": self.size_match,
            "fullness_direction": self.fullness_direction,
            "fullness_mm": round(self.fullness_mm, 1) if self.fullness_mm is not None else None,
            "clearance": self.clearance,
            "quality": self.quality,
            "explanation": self.explanation,
            "footprint_png_base64": self.footprint_png_base64,
            "limitations": list(self.limitations),
        }


def _fullness_estimate(tight_zones: list, loose_zones: list) -> float:
    """How many mm to add (tight) or remove (loose), estimated from the
    worst single-direction squeeze/room across the affected zones -- the same
    per-direction values fit_clearance already classifies zones on, not the
    zone average (§12 of the audit: averaging a medial squeeze against a
    dorsal void reports a comfortable fit nobody feels)."""
    if tight_zones:
        worst = min(
            (v for z in tight_zones for k, v in (z.directional_mm or {}).items()
             if k != "plantar" and v is not None),
            default=None,
        )
        return abs(worst) if worst is not None else 0.0
    room = [z.signed_gap_mm["median"] for z in loose_zones]
    return float(np.mean(room)) if room else 0.0


def _has_directional_conflict(zone, sigma: float) -> bool:
    """A single zone can be squeezed on one axis and slack on another at the
    very same Y level -- narrow in width but tall in height, or the reverse.
    fit_clearance's own per-zone classifier already picks the worst direction
    to label the zone LOCAL_TIGHTNESS or LOCAL_LOOSENESS (§12 of the audit),
    which is right for that zone in isolation, but it means the label alone
    cannot tell "uniformly narrow" from "narrow AND tall" -- both zones get
    called LOCAL_TIGHTNESS. A real pair confirmed this: every zone from heel
    to ball read LOCAL_TIGHTNESS (medial/lateral squeeze up to -8mm), and the
    pipeline reported it as needing a wider fullness, but an independent
    per-Y-level cross-section check found the last was ALSO 6-13mm taller
    than the foot at every one of those same levels -- a misallocated-volume
    last (narrow-and-high), not a uniformly-narrow one. Regrading to a wider
    fullness would not fix a last that is already too tall; it needs
    reshaping. So this checks the zone's own directional_mm, not just its
    single-label classification.
    """
    d = zone.directional_mm or {}
    width = [v for k, v in d.items() if k in ("medial", "lateral") and v is not None]
    dorsal = d.get("dorsal")
    if not width or dorsal is None:
        return False
    if min(width) < -sigma and dorsal > sigma:
        return True  # narrow-and-high
    if max(width) > sigma and dorsal < -sigma:
        return True  # wide-and-low
    return False


def _classify(clearance: ClearanceReport) -> tuple[str, str | None, float | None]:
    """§17.1: no winner-takes-all. The class summarises the zone profile, and
    the per-zone detail stays in the report for the reader to disagree with.

    Returns (fit_class, fullness_direction, fullness_mm). The fullness fields
    are only set for FIT_REQUIRES_DIFFERENT_FULLNESS.
    """
    if not clearance.zones:
        return FIT_INDETERMINATE, None, None
    sigma = clearance.uncertainty.total_sigma_mm
    tight = [z for z in clearance.zones if z.classification == "LOCAL_TIGHTNESS"]
    loose = [z for z in clearance.zones if z.classification == "LOCAL_LOOSENESS"]
    # Only zones fit_clearance actually judged tight or loose can carry a
    # shape verdict. A NOT_SEATED zone is one it explicitly could not judge --
    # the flat-scanned foot hanging over the last's toe spring -- and its
    # per-direction numbers are that gap, not the last's shape. Reading them
    # as "narrow and tall" contradicted the same report's own caveat and, on
    # the pair a wearer reported as loose everywhere, was the last thing still
    # forcing FIT_REQUIRES_LAST_MODIFICATION after every real conflict had
    # cleared.
    judged = [z for z in clearance.zones
              if z.classification in ("LOCAL_TIGHTNESS", "LOCAL_LOOSENESS")]
    conflicted = any(_has_directional_conflict(z, sigma) for z in judged)

    if (tight and loose) or conflicted:
        # Both broad tightness AND broad looseness at once (or a single zone
        # squeezed on one axis and slack on another) is a misallocated-volume
        # pattern (narrow-and-high, wide-and-low, ...), not "one width grade
        # up/down would fix it" -- that needs the last reshaped, not just
        # regraded.
        return FIT_REQUIRES_LAST_MODIFICATION, None, None
    if len(tight) >= _MANY_TIGHT_ZONES:
        # Broad, uniform tightness on a last already confirmed the right
        # length and ball-line placement (fit_size_match ran first and did not
        # gate) is what a too-narrow width grade looks like on a graded last
        # family -- not a defect needing reshaping.
        return FIT_REQUIRES_DIFFERENT_FULLNESS, "wider", _fullness_estimate(tight, [])
    if len(loose) >= _MANY_TIGHT_ZONES:
        return FIT_REQUIRES_DIFFERENT_FULLNESS, "narrower", _fullness_estimate([], loose)
    if tight:
        return FIT_LOCAL_TIGHTNESS, None, None
    if loose:
        return FIT_LOCAL_LOOSENESS, None, None
    return FIT_GOOD, None, None


def analyze_fit(
    foot_mesh: trimesh.Trimesh,
    last_mesh: trimesh.Trimesh,
    foot_side: str | None = None,
    last_side: str | None = None,
    construction: dict | None = None,
    analysis_mode: str = "STATIC_GEOMETRY",
    include_footprint: bool = True,
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
    if registration.axis_mismatch:
        # Reported rather than absorbed: the swing needed to put this foot on
        # this last's axis is itself a finding, and it caps how much the
        # medial/lateral numbers below can be trusted.
        limitations.append(
            f"the last's heel-to-ball axis differs from this foot's: aligning them "
            f"swung the ball {abs(registration.ball_swing_mm):.0f}mm sideways, so the "
            f"medial/lateral split below is less reliable than the totals"
        )

    # 12. curvilinear sections, square to the foot's own centreline
    centerline = build_centerline(foot_registered)
    sections = [s.as_dict() for s in sections_along(foot_registered, SECTION_FRACTIONS, centerline)] \
        if centerline is not None else []
    if not sections:
        limitations.append("cross-sections unavailable")

    # 13. estimated shoe cavity
    cavity = build_cavity(last_used, construction)

    # 13b. Is this last even the right size for this foot? Runs before the
    # zone analysis because a size mismatch makes those zones consequences
    # rather than independent findings (see fit_size_match).
    last_landmarks = detect_foot_landmarks(last_used, side=last_side or foot_side)
    size_match = evaluate_size_match(foot_registered, cavity.mesh,
                                     foot_landmarks, last_landmarks)

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

    footprint = None
    if include_footprint:
        try:
            footprint = render_footprint_overlay(foot_registered, cavity.mesh)
        except Exception as exc:
            limitations.append(f"footprint overlay unavailable: {exc}")

    if size_match.gate_triggered:
        fit_class, fullness_direction, fullness_mm = FIT_STRUCTURALLY_INCOMPATIBLE, None, None
    else:
        fit_class, fullness_direction, fullness_mm = _classify(clearance)
    if size_match.gate_triggered:
        limitations.append(
            "size/proportion mismatch dominates: the zone findings below are its "
            "consequence, not independent problems"
        )
    limitations.extend(size_match.warnings)

    report = FitReport(
        fit_class=fit_class,
        confidence=confidence,
        analysis_mode=analysis_mode,
        landmarks=foot_landmarks.as_dict(),
        registration=registration.as_dict(),
        working_orientation=orientation.as_dict(),
        cavity=cavity.as_dict(),
        sections=sections,
        size_match=size_match.as_dict(),
        fullness_direction=fullness_direction,
        fullness_mm=fullness_mm,
        clearance=clearance.as_dict(),
        quality={"foot": foot_quality.as_dict(), "cavity": last_quality.as_dict()},
        footprint_png_base64=footprint,
        limitations=limitations,
    )
    # Plain-language findings are derived from the finished report, so the text
    # and the numbers can never disagree.
    report.explanation = explain(report.as_dict()).as_dict()
    return report
