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
from app.services.fit_size_match import LENGTH_ALLOWANCE_ACCEPTABLE, evaluate_size_match
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

# Multiples of the clearance uncertainty budget. _CONFLICT_SIGMA matches the
# bar fit_clearance itself uses; _DOMINANCE_RATIO is how much bigger one side
# has to be before it is treated as the story rather than half of a
# misallocated-volume pattern.
_CONFLICT_SIGMA = 2.0

# Repeatability, measured rather than assumed: the same physical last (4977/44
# fullness 12) scanned twice and both scans run through this pipeline against
# the same foot.
#
# Zone clearances came back within 0.57mm on average and 1.62mm at worst -- far
# tighter than the 2.69mm *absolute* budget, because most of that budget (the
# foot's own scan and landmarks, the cavity model) is common to both sides of a
# comparison and cancels out of the difference.
#
# Length did not: 306.5mm against 298.8mm, a 7.7mm spread, and percentile
# trimming does not remove it because it is real geometry -- one scan tapers to
# a 16x8mm tip while the other stops at a 29x10mm cross-section, i.e. the toe
# was captured differently. So a length-driven difference below ~7mm says
# nothing about the lasts, only about the scans.
_ZONE_REPEATABILITY_MM = 1.6
_LENGTH_REPEATABILITY_MM = 7.0

# Ranking order, best first. Looseness sits above tightness on purpose: slack
# is a fixation problem and partly recoverable with lacing or an insole, while
# a press has nowhere to go. Used only to order results -- it asserts nothing
# the classes themselves do not already say.
FIT_CLASS_ORDER = {
    FIT_GOOD: 0,
    FIT_LOCAL_LOOSENESS: 1,
    FIT_LOCAL_TIGHTNESS: 2,
    FIT_REQUIRES_DIFFERENT_FULLNESS: 3,
    FIT_REQUIRES_LAST_MODIFICATION: 4,
    FIT_STRUCTURALLY_INCOMPATIBLE: 5,
    FIT_INDETERMINATE: 6,
}
_DOMINANCE_RATIO = 2.0


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
    # Ordering aids: which class this is (best-first) and how far outside
    # acceptable its worst reading sits. See _worst_deviation_mm.
    class_order: int = 0
    worst_deviation_mm: float = 0.0
    deviation_source: str = "none"
    # How small a difference in worst_deviation_mm is still meaningful, given
    # what produced it. See _ZONE_REPEATABILITY_MM / _LENGTH_REPEATABILITY_MM.
    deviation_resolution_mm: float = _ZONE_REPEATABILITY_MM
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
            "class_order": self.class_order,
            "worst_deviation_mm": self.worst_deviation_mm,
            "deviation_source": self.deviation_source,
            "deviation_resolution_mm": self.deviation_resolution_mm,
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
    # Same bar fit_clearance uses to call a zone tight or loose at all. It used
    # to be 1 sigma here while the zone classifier moved to 2, and a pair of
    # readings each within half a millimetre of the noise floor (lateral -2.7,
    # dorsal +3.2, sigma 2.69) was enough to promote a whole last to "needs
    # reshaping" -- the most severe verdict there is, off the weakest evidence
    # the report contains.
    bar = _CONFLICT_SIGMA * sigma
    if min(width) < -bar and dorsal > bar:
        return True  # narrow-and-high
    if max(width) > bar and dorsal < -bar:
        return True  # wide-and-low
    return False


def _worst_deviation_mm(clearance: ClearanceReport, size_match) -> tuple[float, str]:
    """The largest single "how many mm outside acceptable" across every check,
    so two lasts in the same class can still be told apart.

    Deliberately one number over mixed units: within a class the reader is
    asking "which of these is further off", and the honest answer is the worst
    thing about each. The detail behind it stays in the findings.
    """
    sigma = clearance.uncertainty.total_sigma_mm
    worst, source = 0.0, "none"
    for z in clearance.zones:
        if z.classification == "LOCAL_TIGHTNESS":
            squeeze = min((v for k, v in (z.directional_mm or {}).items()
                           if k != "plantar" and v is not None), default=0.0)
            if abs(min(squeeze, 0.0)) > worst:
                worst, source = abs(min(squeeze, 0.0)), "zone"
        elif z.classification == "LOCAL_LOOSENESS":
            room = z.signed_gap_mm["median"] - 2.0 * sigma
            if room > worst:
                worst, source = room, "zone"
    allowance = getattr(size_match, "length_allowance_mm", None)
    if allowance is not None:
        lo, hi = LENGTH_ALLOWANCE_ACCEPTABLE
        off = max(allowance - hi, lo - allowance)
        if off > worst:
            worst, source = off, "length"
    return round(max(worst, 0.0), 1), source


def _broadly_tight(zones: list, sigma: float) -> list:
    """Zones tight in their bulk, not merely in their tail.

    fit_clearance flags a zone as LOCAL_TIGHTNESS on either its worst
    direction or its p05 -- the worst 5% of samples. The p05 route is right
    for spotting a local press, but it is not evidence that a whole last is
    the wrong width grade, and treating it as such made the fullness verdict
    hinge on noise: Prada 43 and 44 read within a millimetre of each other in
    every zone (p05 -5.6/-5.8/-6.0 against -5.4/-5.8/-4.2, threshold -5.4),
    yet one landed on "нужна другая полнота" and the other on "локальная
    теснота" purely because a third zone crossed by 0.6mm. A grade is wrong
    only if the zones are tight through their middle too.
    """
    out = []
    for z in zones:
        worst = min((v for k, v in (z.directional_mm or {}).items()
                     if k != "plantar" and v is not None), default=0.0)
        if z.signed_gap_mm["median"] < -sigma or worst < -_CONFLICT_SIGMA * sigma:
            out.append(z)
    return out


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

    if conflicted:
        # A single zone squeezed on one axis and slack on another is a
        # misallocated-volume pattern (narrow-and-high, wide-and-low, ...),
        # not "one width grade up/down would fix it" -- that needs the last
        # reshaped, not just regraded.
        return FIT_REQUIRES_LAST_MODIFICATION, None, None

    if tight and loose:
        # Tightness and looseness together mean misallocated volume only when
        # they are of comparable size. Without that check the rule was blind to
        # magnitude: one small press outranked broad, much larger slack and
        # headlined a last as needing reshaping when the honest reading was
        # "roomy, with a local press". When one side clearly dominates, it is
        # the verdict, and the other stays as its own finding below.
        tight_mag = _fullness_estimate(tight, [])
        loose_mag = _fullness_estimate([], loose)
        weaker = min(tight_mag, loose_mag)
        if weaker <= 0 or max(tight_mag, loose_mag) < _DOMINANCE_RATIO * weaker:
            return FIT_REQUIRES_LAST_MODIFICATION, None, None
        if tight_mag > loose_mag:
            loose = []
        else:
            tight = []
    broad = _broadly_tight(tight, sigma)
    if len(broad) >= _MANY_TIGHT_ZONES:
        # Broad, uniform tightness on a last already confirmed the right
        # length and ball-line placement (fit_size_match ran first and did not
        # gate) is what a too-narrow width grade looks like on a graded last
        # family -- not a defect needing reshaping.
        return FIT_REQUIRES_DIFFERENT_FULLNESS, "wider", _fullness_estimate(broad, [])
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

    # 13a. Seat the foot inside the cavity rather than on the last.
    #
    # Registration pins the heel to the *last*, which is right: the last is
    # the reference shape and §9 wants that anchor exact. But clearance is
    # measured against the cavity, whose back has moved forward by the heel
    # counter's thickness and whose floor has risen by the insole's. Left
    # uncorrected, the foot's heel hangs behind the cavity's back and its sole
    # sits below the cavity's floor -- a constant offset that shows up as
    # tightness at the posterior heel for *every* foot against *every* last.
    # Measured: the foot's rearmost point 3.0mm behind the cavity's, and the
    # posterior-heel zone reading a median -3.0mm at sole level as a result.
    # In a real shoe the heel rests against the inside of the counter and the
    # foot stands on top of the insole, which is exactly this shift.
    fv_reg = np.asarray(foot_registered.vertices, dtype=float)
    cv = np.asarray(cavity.mesh.vertices, dtype=float)
    seating_shift = np.array([0.0,
                              float(cv[:, 1].min() - fv_reg[:, 1].min()),
                              float(cv[:, 2].min() - fv_reg[:, 2].min())])
    if np.any(np.abs(seating_shift) > 1e-9):
        foot_registered = foot_registered.copy()
        foot_registered.apply_translation(seating_shift)
        limitations.append(
            f"foot seated inside the cavity (+{seating_shift[1]:.1f}mm along the foot, "
            f"+{seating_shift[2]:.1f}mm up) so the counter and insole thicknesses are "
            "not read as heel tightness"
        )

    # 13b. Is this last even the right size for this foot? Runs before the
    # zone analysis because a size mismatch makes those zones consequences
    # rather than independent findings (see fit_size_match).
    last_landmarks = detect_foot_landmarks(last_used, side=last_side or foot_side)
    size_match = evaluate_size_match(foot_registered, cavity.mesh,
                                     foot_landmarks, last_landmarks,
                                     last_mesh=last_used,
                                     foot_length_mm=float(
                                         np.ptp(np.asarray(foot_aligned.vertices)[:, 1])))

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

    deviation, deviation_source = _worst_deviation_mm(clearance, size_match)

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
        class_order=FIT_CLASS_ORDER.get(fit_class, 6),
        worst_deviation_mm=deviation,
        deviation_source=deviation_source,
        deviation_resolution_mm=(_LENGTH_REPEATABILITY_MM if deviation_source == "length"
                                 else _ZONE_REPEATABILITY_MM),
        clearance=clearance.as_dict(),
        quality={"foot": foot_quality.as_dict(), "cavity": last_quality.as_dict()},
        footprint_png_base64=footprint,
        limitations=limitations,
    )
    # Plain-language findings are derived from the finished report, so the text
    # and the numbers can never disagree.
    report.explanation = explain(report.as_dict()).as_dict()
    return report
