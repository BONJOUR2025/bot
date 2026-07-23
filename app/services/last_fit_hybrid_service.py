"""hybrid_v2: the combined mesh-based comparison — stage 6 of the
slice_v1 -> hybrid_v2 migration (see docs/last_fit_system_overview.md and
the migration plan).

This wires together every earlier stage (mesh quality + repair, stage 2;
surface distance, stage 3; anatomical registration, stage 4; pose, stage 5)
into one comparison, and adds the two things stage 6 itself is responsible
for: connected/zone-level conflict summaries with a *direction*
(medial/lateral/dorsal/plantar), and simple combinational patterns
(NARROW_HIGH, WIDE_LOW, ...) recognizing that a real fit problem is a
combination of signals, not one winning scalar — exactly last_fit_service.py's
own module docstring's headline example (ΔG>=0, ΔW>0, ΔH<0: "girth is
redistributed into width, not height").

Scoped-down from the migration plan's full ask, with the reason spelled out
rather than silently skipped:

- True per-face connected-component clustering of the negative-distance
  region (plan §11: "mesh.face_adjacency + BFS") would need signed distance
  computed at full mesh resolution (~110k faces on a real scan) — the same
  cost stage 3 already found made a plain per-vertex query blow up to
  7GB/80s. This module works at the same bounded sample size stage 3
  established instead, bucketed by the *existing* 5-zone convention
  (`last_fit_service.ZONES`) rather than a free-form connected-region
  graph — "which named zone is in conflict" instead of "the arbitrary
  bounding shape of the conflict".
- Directional clearance is derived from the already-computed sample points'
  own position (medial: x>=0, lateral: x<0, matching the existing
  medial/lateral convention in scm_parser_service.extract_profile; dorsal:
  above the zone's own median height, plantar: below it) rather than
  additional ray-casts — reuses data already paid for in stage 3, no new
  expensive queries.
- posterior_clearance (plan §13) isn't computed — the heel's "behind" edge
  isn't well-defined for a closed mesh in the same medial/lateral/dorsal/
  plantar sense and needs its own treatment; left for a follow-up rather than
  faked.

`overall`/`legacy_slice_result` stay whatever slice_v1 already produces
(`last_fit_service.compare_profiles`, untouched) — this module's output is
returned *alongside* that, per the migration plan (§6.9): hybrid_v2 adds a
`surface_result`, it doesn't replace the frozen slice_v1 numbers.
"""
from __future__ import annotations

import numpy as np
import trimesh

from app.services.last_pose_service import apply_pose
from app.services.last_registration_service import register_foot_to_cavity
from app.services.mesh3d_service import (
    bidirectional_surface_distance,
    distance_aggregates,
    mesh_quality_report,
    repair_small_holes,
)

# Same 5 zones/boundaries as last_fit_service.ZONES, restated here rather than
# imported — last_fit_service's ZONES is a private-ish module constant tied to
# its own profile-array indexing; this module buckets raw (x,y,z) sample
# points by the same length fractions, a different mechanism reaching the
# same named zones on purpose (so surface_result and legacy_slice_result talk
# about the same 5 zones and stay comparable side by side).
ZONES = [
    ("heel", 0.00, 0.25, "Пятка"),
    ("waist", 0.25, 0.42, "Свод / талия"),
    ("instep", 0.42, 0.60, "Подъём"),
    ("ball", 0.60, 0.78, "Пучки (широкая часть)"),
    ("toe", 0.78, 1.00, "Носок (пальцы)"),
]
_MIN_ZONE_SAMPLES = 5

# Pattern thresholds (mm, foot->cavity signed distance: >0 room, <0 conflict).
# Deliberately the same order of magnitude as last_fit_service.py's own
# PROTRUSION_MM/ZONE_WIDTH_LOOSE_MM — engineering starting points, not
# independently calibrated for this mesh-based path (see module docstring on
# what stage 9 -- calibration -- would still need to do).
_WIDTH_TIGHT_MM = -2.0
_WIDTH_LOOSE_MM = 4.0
_HEIGHT_TIGHT_MM = -2.0
_HEIGHT_LOOSE_MM = 4.0

NARROW_HIGH = "NARROW_HIGH"
WIDE_LOW = "WIDE_LOW"
MEDIAL_CONFLICT_DORSAL_VOID = "MEDIAL_CONFLICT_DORSAL_VOID"
BALL_TIGHT_INSTEP_LOOSE = "BALL_TIGHT_INSTEP_LOOSE"
HEEL_VOID_MIDFOOT_TIGHT = "HEEL_VOID_MIDFOOT_TIGHT"
GENERAL_OVERSIZE = "GENERAL_OVERSIZE"


def _zone_directional_summary(points: np.ndarray, normals: np.ndarray, distances: np.ndarray,
                               zone_lo: float, zone_hi: float, foot_length_mm: float) -> dict | None:
    """medial/lateral/dorsal/plantar clearance for one zone, classified by
    each sampled point's own surface-normal direction rather than raw
    position. Position alone is misleading on anything but a perfectly
    round cross-section: a point on the *top* of a wide, flat foot can still
    have x>=0 despite facing straight up (+Z), not sideways — its normal is
    what actually says which direction it "faces". Each point is assigned to
    whichever of X/Z its normal points along most strongly (dominant-axis
    classification), so a side-wall point (normal ~ +-X) never gets counted
    as dorsal/plantar and vice versa.

    Known limitation (found while testing this against synthetic geometry
    with a large height mismatch): a medial/lateral-facing point whose height
    sits above the *other* mesh's own height range doesn't have a same-height
    counterpart on that mesh's side wall — its true nearest point may fall on
    that mesh's top edge/face instead, mixing a width reading with what's
    really a height signal. Harmless for the height gaps seen on this
    scanner's real reference scans; a foot/last pair with a much larger
    height mismatch than that could see medial/lateral clearance pulled
    toward the dorsal/plantar value at the extremes of a zone's height range.
    """
    y = points[:, 1]
    frac = y / foot_length_mm
    finite = np.isfinite(distances)
    in_zone = (frac >= zone_lo) & (frac < zone_hi) & finite
    if in_zone.sum() < _MIN_ZONE_SAMPLES:
        return None
    nx, nz, zd = normals[in_zone, 0], normals[in_zone, 2], distances[in_zone]
    horizontal_dominant = np.abs(nx) >= np.abs(nz)

    def _mean(mask) -> float | None:
        return float(np.mean(zd[mask])) if mask.any() else None

    return {
        "n": int(in_zone.sum()),
        "medial_clearance_mm": _mean(horizontal_dominant & (nx >= 0)),
        "lateral_clearance_mm": _mean(horizontal_dominant & (nx < 0)),
        "dorsal_clearance_mm": _mean(~horizontal_dominant & (nz >= 0)),
        "plantar_clearance_mm": _mean(~horizontal_dominant & (nz < 0)),
    }


# Same reasoning as last_fit_service.py's ZONE_HEIGHT_MATTERS: foot scans
# include the ankle/shin (see mesh3d_service.py's module docstring — no clean
# cut point was found, so it's still there in the mesh), and in heel/waist
# that column of extra height is anatomy the last was never meant to enclose
# in the first place, not a real dorsal conflict/void. Trusting a dorsal/
# plantar reading there would just be re-measuring the shin. Ball/instep are
# where the upper genuinely wraps over the top of the foot.
_ZONE_HEIGHT_MATTERS = {"heel": False, "waist": False, "instep": True, "ball": True, "toe": False}


def _classify_zone_pattern(zone_key: str, directional: dict | None) -> str | None:
    if directional is None:
        return None
    m = directional["medial_clearance_mm"]
    l = directional["lateral_clearance_mm"]
    d = directional["dorsal_clearance_mm"] if _ZONE_HEIGHT_MATTERS.get(zone_key, False) else None

    width_tight = (m is not None and m < _WIDTH_TIGHT_MM) or (l is not None and l < _WIDTH_TIGHT_MM)
    width_loose = (m is not None and m > _WIDTH_LOOSE_MM) and (l is not None and l > _WIDTH_LOOSE_MM)
    height_loose = d is not None and d > _HEIGHT_LOOSE_MM
    height_tight = d is not None and d < _HEIGHT_TIGHT_MM

    # Order matters: the doc's headline diagnostic case is width-tight with
    # a dorsal void (girth/volume redistributed away from where it's needed).
    if width_tight and height_loose:
        return NARROW_HIGH
    if width_loose and height_tight:
        return WIDE_LOW
    if m is not None and m < _WIDTH_TIGHT_MM and height_loose:
        return MEDIAL_CONFLICT_DORSAL_VOID
    return None


def _zone_width_ease(directional: dict | None) -> float | None:
    """Average of medial+lateral clearance — a width-only signal, deliberately
    not the omnidirectional aggregate (which mixes in the dorsal/plantar
    reading, contaminated by shin/ankle geometry in heel/waist — see
    _ZONE_HEIGHT_MATTERS above). Used for every *cross-zone* width comparison
    below, including ball/instep, for the same reason it's not fine to mix
    directions there either — a width comparison should stay a width
    comparison."""
    if directional is None:
        return None
    values = [v for v in (directional["medial_clearance_mm"], directional["lateral_clearance_mm"])
              if v is not None]
    return float(np.mean(values)) if values else None


def _cross_zone_patterns(width_ease: dict[str, float | None]) -> list[str]:
    patterns: list[str] = []
    ball, instep = width_ease.get("ball"), width_ease.get("instep")
    if ball is not None and instep is not None:
        if ball < _WIDTH_TIGHT_MM and instep > _WIDTH_LOOSE_MM:
            patterns.append(BALL_TIGHT_INSTEP_LOOSE)
    heel, waist = width_ease.get("heel"), width_ease.get("waist")
    if heel is not None and waist is not None:
        if heel > _WIDTH_LOOSE_MM and waist < _WIDTH_TIGHT_MM:
            patterns.append(HEEL_VOID_MIDFOOT_TIGHT)
    values = [v for v in width_ease.values() if v is not None]
    if values and all(v > _WIDTH_LOOSE_MM for v in values):
        patterns.append(GENERAL_OVERSIZE)
    return patterns


def _risk_scores(width_ease: dict[str, float | None]) -> tuple[float, float]:
    """Bounded 0..1 heuristics (not calibrated probabilities — see module
    docstring), averaging how far each zone's width ease sits past 0 in each
    direction, normalized against a 10mm "severe" scale."""
    values = [v for v in width_ease.values() if v is not None]
    if not values:
        return 0.0, 0.0
    tightness = float(np.clip(np.mean([max(0.0, -v) for v in values]) / 10.0, 0.0, 1.0))
    looseness = float(np.clip(np.mean([max(0.0, v) for v in values]) / 10.0, 0.0, 1.0))
    return tightness, looseness


def _retention_risk(heel_directional: dict | None, registration_confidence: float) -> float:
    if heel_directional is None:
        return 0.0
    m, l = heel_directional["medial_clearance_mm"], heel_directional["lateral_clearance_mm"]
    if m is None or l is None:
        return 0.0
    # Same principle as last_fit_service's symmetric-looseness check: slack
    # on only one side is a registration/alignment artifact, not real heel
    # slip risk -- take the smaller (more conservative) of the two sides.
    loose_both = min(m, l)
    base = float(np.clip(loose_both / 8.0, 0.0, 1.0)) if loose_both > 0 else 0.0
    # A shaky registration shouldn't be allowed to produce a confident-sounding risk.
    return float(np.clip(base * registration_confidence, 0.0, 1.0))


def compare_hybrid(
    foot_mesh: trimesh.Trimesh, foot_side: str | None,
    last_mesh: trimesh.Trimesh, last_side: str | None,
    heel_height_mm: float | None = None, toe_spring_mm: float | None = None,
) -> dict:
    """Full hybrid_v2 comparison. Synchronous/CPU-bound — run via
    asyncio.to_thread, like the slice_v1 comparison it runs alongside."""
    foot_quality = mesh_quality_report(foot_mesh)
    cavity_quality = mesh_quality_report(last_mesh)

    foot_repaired, foot_was_repaired = repair_small_holes(foot_mesh)
    cavity_repaired, cavity_was_repaired = repair_small_holes(last_mesh)
    if foot_was_repaired:
        foot_quality = mesh_quality_report(foot_repaired)
    if cavity_was_repaired:
        cavity_quality = mesh_quality_report(cavity_repaired)

    posed_foot, pose_confidence = apply_pose(foot_repaired, heel_height_mm, toe_spring_mm)

    registration, foot_aligned, cavity_aligned = register_foot_to_cavity(
        posed_foot, foot_side, cavity_repaired, last_side,
    )
    final_foot = foot_aligned.copy()
    final_foot.vertices = registration.aligned_foot_vertices
    foot_length_mm = float(final_foot.vertices[:, 1].max())

    bidir = bidirectional_surface_distance(final_foot, foot_quality, cavity_aligned, cavity_quality)
    f2c = bidir["foot_to_cavity"]  # conflict/contact/room right at the foot's own surface

    zone_aggregates: dict[str, dict | None] = {}
    zone_directional: dict[str, dict | None] = {}
    zone_patterns: list[dict] = []
    for key, lo, hi, label in ZONES:
        frac = f2c["points"][:, 1] / foot_length_mm
        in_zone = (frac >= lo) & (frac < hi)
        n = int(in_zone.sum())
        zone_aggregates[key] = (
            distance_aggregates(f2c["distances"][in_zone], bidir["foot_surface_area_mm2"])
            if n >= _MIN_ZONE_SAMPLES else None
        )
        directional = _zone_directional_summary(f2c["points"], f2c["normals"], f2c["distances"], lo, hi, foot_length_mm)
        zone_directional[key] = directional
        pattern = _classify_zone_pattern(key, directional)
        if pattern:
            zone_patterns.append({"zone": key, "label": label, "pattern": pattern})

    width_ease = {key: _zone_width_ease(zone_directional[key]) for key, _lo, _hi, _label in ZONES}
    cross_patterns = [{"zone": None, "label": None, "pattern": p}
                       for p in _cross_zone_patterns(width_ease)]
    all_patterns = zone_patterns + cross_patterns
    dominant_pattern = all_patterns[0]["pattern"] if all_patterns else None

    tightness_risk, looseness_risk = _risk_scores(width_ease)
    retention_risk = _retention_risk(zone_directional.get("heel"), registration.registration_confidence)

    return {
        "engine": "hybrid_v2",
        "quality": {
            "foot": foot_quality.as_dict(),
            "cavity": cavity_quality.as_dict(),
            "foot_repaired": foot_was_repaired,
            "cavity_repaired": cavity_was_repaired,
            "signed_distance_valid": f2c["signed"],
        },
        "registration": registration.as_dict(),
        "pose_confidence": pose_confidence,
        "zones": {
            key: {
                "label": label,
                "aggregate": zone_aggregates[key],
                "directional": zone_directional[key],
            }
            for key, _lo, _hi, label in ZONES
        },
        "patterns": all_patterns,
        "dominant_pattern": dominant_pattern,
        "risks": {
            "tightness_risk": round(tightness_risk, 3),
            "looseness_risk": round(looseness_risk, 3),
            "retention_risk": round(retention_risk, 3),
        },
    }
