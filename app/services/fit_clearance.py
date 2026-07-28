"""Signed and directional clearance between a posed foot and a shoe cavity,
summarised over anatomical zones, with an explicit uncertainty budget --
§13, §16 and §18 of research_foot_last_pose_fit_technical_report_for_claude.md.

Three things distinguish this from the zone summaries in
last_fit_hybrid_service:

- Clearance is measured against the *cavity* (shoe_cavity.py), not the last.
- Direction matters (§13.2): a nearest-point distance says how far, never
  which way. Medial, lateral, dorsal and plantar clearance are reported
  separately, classified by the foot's own surface normal rather than by the
  sign of a coordinate (a point can sit at x>0 while its surface faces up).
- Nothing is called pressure (§11.6, §25.3). Without a validated mechanical
  model with materials and load, the honest vocabulary is geometric
  interference and required compression, and that is what is reported.

Uncertainty (§18) is carried as separate components rather than one blended
number, because they have genuinely different sources and a reader has to be
able to see which one dominates. §13.6 is the reason it matters: 3D scanning
itself is only good to roughly 0.7-1.5mm, so a 1mm "conflict" is not evidence
of anything, and after pose estimation the budget is larger still.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh
from scipy.spatial import cKDTree

from app.services.mesh3d_service import MeshQualityReport, _sample_surface_points

# §16 zone model, as fractions of foot length with a dorsal/plantar split.
# Fewer than the document's 16 named zones: the ones omitted (separate ankle
# zones, per-toe splits) need landmarks this pipeline does not yet locate, and
# inventing boundaries for them would be false precision.
ZONES: tuple[tuple[str, str, float, float], ...] = (
    ("Z01", "posterior_heel", 0.00, 0.08),
    ("Z02", "heel", 0.08, 0.25),
    ("Z04", "waist", 0.25, 0.42),
    ("Z07", "instep", 0.42, 0.60),
    ("Z08", "ball", 0.60, 0.78),
    ("Z13", "toes", 0.78, 0.95),
    ("Z14", "toe_tip", 0.95, 1.01),
)

# §18.1 component sigmas, in mm. Scan figures follow §13.6's reported range for
# 3D foot scanning; the pose figure follows §10.4/§13.6, where a statistical
# dynamic shape model reported ~5mm RMSE. These are documented assumptions,
# not calibrated constants -- §29 asks for a fitting pilot before any of them
# is treated as fact.
SIGMA_SCAN_MM = 1.0
SIGMA_LANDMARK_MM = 2.0
SIGMA_CAVITY_PROXY_MM = 1.5
SIGMA_POSE_APPLIED_MM = 5.0
SIGMA_POSE_NONE_MM = 0.0

_DIRECTION_MIN_SAMPLES = 8

# How many nearest cavity vertices (in plan view) define the local ceiling
# above a foot sample. Enough to span a facet or two so a single stray
# vertex cannot lower the bound, few enough to stay local to the cone.
_TOPLINE_NEIGHBOURS = 32


@dataclass
class ZoneClearance:
    zone_id: str
    name: str
    n_samples: int
    signed_gap_mm: dict          # min/p05/median/p95 -- positive = room
    required_compression_mm: dict
    conflict_area_mm2: float
    directional_mm: dict         # medial/lateral/dorsal/plantar medians
    seating_gap_mm: float | None  # plantar: how far the foot sits off the sole
    classification: str
    confidence: float

    def as_dict(self) -> dict:
        return {
            "zone_id": self.zone_id,
            "name": self.name,
            "n_samples": self.n_samples,
            "signed_gap_mm": self.signed_gap_mm,
            "required_compression_mm": self.required_compression_mm,
            "conflict_area_mm2": round(self.conflict_area_mm2, 1),
            "directional_mm": self.directional_mm,
            "seating_gap_mm": self.seating_gap_mm,
            "classification": self.classification,
            "confidence": round(self.confidence, 3),
        }


@dataclass
class UncertaintyBudget:
    scan_sigma_mm: float
    landmark_sigma_mm: float
    cavity_sigma_mm: float
    pose_sigma_mm: float

    @property
    def total_sigma_mm(self) -> float:
        """§10.8 of the audit: independent contributions add in quadrature."""
        return float(np.sqrt(self.scan_sigma_mm ** 2 + self.landmark_sigma_mm ** 2
                             + self.cavity_sigma_mm ** 2 + self.pose_sigma_mm ** 2))

    def as_dict(self) -> dict:
        return {
            "scan_sigma_mm": round(self.scan_sigma_mm, 2),
            "landmark_sigma_mm": round(self.landmark_sigma_mm, 2),
            "cavity_sigma_mm": round(self.cavity_sigma_mm, 2),
            "pose_sigma_mm": round(self.pose_sigma_mm, 2),
            "total_sigma_mm": round(self.total_sigma_mm, 2),
            "note": "geometric interference only; not a pressure or a measured shoe interior",
        }


@dataclass
class ClearanceReport:
    zones: list[ZoneClearance]
    uncertainty: UncertaintyBudget
    cavity_mode: str
    analysis_mode: str
    signed: bool
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "analysis_mode": self.analysis_mode,
            "cavity_mode": self.cavity_mode,
            "signed_distance_valid": self.signed,
            "zones": [z.as_dict() for z in self.zones],
            "uncertainty": self.uncertainty.as_dict(),
            "limitations": list(self.limitations),
        }


def _classify(median_gap: float, p05_gap: float, conflict_area: float,
              sigma: float, seating_mm: float | None, directional: dict | None) -> str:
    """§13.5/§17: a classification has to survive the uncertainty budget, and
    a conflict smaller than the measurement noise is not a finding.

    Plantar-facing gaps are handled apart from tightness. A negative gap
    against the shoe's own floor does not mean the shoe squeezes the foot --
    the foot rests *on* the insole, it cannot sink through it. On the real
    Prada 43 the toe-tip plantar reading was -21.6mm, matching that last's
    +21.57mm toe spring exactly: a flat-scanned foot laid against a sprung
    sole, which §3.2 names as a false conflict produced by comparing without a
    pose transformation. Reporting it as "tight" would be simply wrong.
    """
    if seating_mm is not None and seating_mm < -3.0 * max(sigma, 1.0):
        return "NOT_SEATED"

    # Judge on the *worst direction*, not on the zone average. §12 of the audit
    # objects to exactly that averaging: a zone can be pinched medially by 9mm
    # while sitting 6mm loose dorsally, and the mean of the two reports a
    # comfortable fit that nobody experiences. Measured on the real pair, the
    # ball zone reads +3.2mm on average and -9.2mm medially -- the medial
    # number is the one the wearer feels.
    worst_squeeze = min((v for k, v in (directional or {}).items()
                         if k != "plantar" and v is not None), default=None)
    if worst_squeeze is not None and worst_squeeze < -sigma:
        return "LOCAL_TIGHTNESS"
    if p05_gap < -2.0 * sigma:
        return "LOCAL_TIGHTNESS"
    if median_gap > 3.0 * max(sigma, 1.0):
        return "LOCAL_LOOSENESS"
    if abs(median_gap) <= sigma:
        return "WITHIN_UNCERTAINTY"
    return "ACCEPTABLE"


def _directional_medians(points: np.ndarray, normals: np.ndarray,
                          gaps: np.ndarray) -> dict:
    """Split clearance by which way the foot's surface faces (§13.2).

    Classified by the dominant axis of the surface normal, not by coordinate
    sign -- a point on a flat instep can sit at x>0 while facing straight up,
    and calling that "medial clearance" is how a dorsal void gets reported as a
    width problem.
    """
    out: dict[str, float | None] = {"medial": None, "lateral": None,
                                    "dorsal": None, "plantar": None}
    if len(normals) == 0:
        return out
    nx, nz = normals[:, 0], normals[:, 2]
    horizontal = np.abs(nx) >= np.abs(nz)
    buckets = {
        "medial": horizontal & (nx >= 0),
        "lateral": horizontal & (nx < 0),
        "dorsal": (~horizontal) & (nz >= 0),
        "plantar": (~horizontal) & (nz < 0),
    }
    for key, mask in buckets.items():
        if mask.sum() >= _DIRECTION_MIN_SAMPLES:
            out[key] = round(float(np.median(gaps[mask])), 2)
    return out


def compute_clearance(
    foot_mesh: trimesh.Trimesh,
    cavity_mesh: trimesh.Trimesh,
    cavity_quality: MeshQualityReport,
    cavity_mode: str = "LAST_PROXY",
    analysis_mode: str = "STATIC_GEOMETRY",
    pose_applied: bool = False,
    max_sample_points: int = 2000,
) -> ClearanceReport:
    """Signed clearance from the foot's surface to the cavity, summarised by
    zone. Positive = room, negative = the foot wants space the cavity does not
    have (this codebase's established convention, matching §13.1)."""
    limitations: list[str] = []
    points, normals = _sample_surface_points(foot_mesh, max_sample_points)

    # A shoe cavity stops where the shoe does. A foot scan routinely includes
    # the ankle and lower leg, and those points are not "extremely tight" --
    # they are simply outside the shoe, where clearance is undefined. §14 of
    # the audit asks for exactly this: a region the analysis cannot evaluate
    # must say so, because a silent omission reads as an absence of problems.
    #
    # This used to cut at the cavity's single highest point, which on a real
    # last is the top of its mounting cone -- 100mm up, far above any shoe.
    # Everything below that survived the cut, so the foot's ankle was compared
    # against the last's waist and read as a conflict: on the pair that a
    # wearer reported as loose everywhere, the waist zone showed the foot
    # 10.8mm "wider" than the cavity, which was ankle (97mm across at 80-100mm
    # height) against a cone (20-35mm across at the same height).
    #
    # The bound has to be local, because the cone is narrow: a foot sample is
    # inside the shoe only if the cavity still has material above it *at its
    # own x,y*. Taking the highest of the nearest cavity vertices in plan view
    # gives that, and -- unlike a radius query -- it still returns a bound for
    # a foot point that juts out sideways past the cavity wall, which is a
    # real conflict and must not be silently dropped.
    cav_xy = np.asarray(cavity_mesh.vertices, dtype=float)
    _, near = cKDTree(cav_xy[:, :2]).query(points[:, :2], k=_TOPLINE_NEIGHBOURS)
    local_top_z = cav_xy[near, 2].max(axis=1)
    inside_extent = points[:, 2] <= local_top_z
    n_excluded = int((~inside_extent).sum())
    if n_excluded:
        limitations.append(
            f"{n_excluded} of {len(points)} foot samples sit above the cavity "
            "(shin/ankle) and are not_evaluable rather than counted as conflict"
        )
    if inside_extent.sum() < _DIRECTION_MIN_SAMPLES:
        limitations.append("almost_no_foot_samples_inside_cavity_extent")
    else:
        points, normals = points[inside_extent], normals[inside_extent]

    if cavity_quality.valid_for_signed_distance:
        gaps = trimesh.proximity.signed_distance(cavity_mesh, points)
        signed = True
    else:
        _c, dist, _t = trimesh.proximity.closest_point(cavity_mesh, points)
        gaps = dist
        signed = False
        limitations.append("cavity_not_closed_unsigned_distance_only")

    uncertainty = UncertaintyBudget(
        scan_sigma_mm=SIGMA_SCAN_MM,
        landmark_sigma_mm=SIGMA_LANDMARK_MM,
        cavity_sigma_mm=SIGMA_CAVITY_PROXY_MM if cavity_mode == "LAST_PROXY" else 0.5,
        pose_sigma_mm=SIGMA_POSE_APPLIED_MM if pose_applied else SIGMA_POSE_NONE_MM,
    )
    sigma = uncertainty.total_sigma_mm

    y = points[:, 1]
    y_min = float(y.min())
    length = max(float(y.max()) - y_min, 1e-6)
    frac = (y - y_min) / length
    surface_area = float(foot_mesh.area)

    zones: list[ZoneClearance] = []
    for zone_id, name, lo, hi in ZONES:
        in_zone = (frac >= lo) & (frac < hi)
        n = int(in_zone.sum())
        if n < _DIRECTION_MIN_SAMPLES:
            continue
        g = gaps[in_zone]
        finite = g[np.isfinite(g)]
        if finite.size == 0:
            continue

        # Split off the plantar-facing samples: pressing down on the insole is
        # seating, not squeezing (see _classify). Tightness is judged on what
        # is left, so a sprung toe cannot masquerade as a pinched one.
        zone_normals = normals[in_zone]
        zone_gaps = g
        plantar_face = (np.abs(zone_normals[:, 0]) < np.abs(zone_normals[:, 2])) & (zone_normals[:, 2] < 0)
        plantar_face = plantar_face[np.isfinite(g)]
        seating_mm = float(np.median(finite[plantar_face])) if plantar_face.sum() >= _DIRECTION_MIN_SAMPLES else None

        zone_directional = _directional_medians(points[in_zone], normals[in_zone], g)
        squeeze = finite[~plantar_face] if plantar_face.any() else finite
        if squeeze.size == 0:
            squeeze = finite
        conflict = squeeze[squeeze < 0]
        # Area-weighted sampling means a sample fraction is an area fraction.
        conflict_area = float(len(conflict) / len(gaps) * surface_area)
        median_gap = float(np.median(squeeze))
        p05 = float(np.percentile(squeeze, 5))

        zones.append(ZoneClearance(
            zone_id=zone_id, name=name, n_samples=n,
            signed_gap_mm={
                "min": round(float(finite.min()), 2),
                "p05": round(p05, 2),
                "median": round(median_gap, 2),
                "p95": round(float(np.percentile(finite, 95)), 2),
            },
            required_compression_mm={
                "max": round(float(-conflict.min()), 2) if conflict.size else 0.0,
                "p95": round(float(-np.percentile(conflict, 5)), 2) if conflict.size else 0.0,
            },
            conflict_area_mm2=conflict_area,
            directional_mm=zone_directional,
            seating_gap_mm=round(seating_mm, 2) if seating_mm is not None else None,
            classification=_classify(median_gap, p05, conflict_area, sigma, seating_mm, zone_directional),
            # A zone read through a bigger uncertainty budget is worth less.
            confidence=float(np.clip(1.0 - sigma / 12.0, 0.05, 1.0)),
        ))

    if cavity_mode == "LAST_PROXY":
        limitations.append("cavity is an estimate from the last, not a measured shoe interior")
    if pose_applied:
        limitations.append("foot pose is inferred; see §10.4 pose uncertainty")
    limitations.append("geometric interference only -- no pressure is computed")

    return ClearanceReport(zones=zones, uncertainty=uncertainty,
                           cavity_mode=cavity_mode, analysis_mode=analysis_mode,
                           signed=signed, limitations=limitations)
