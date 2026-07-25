"""Anatomical landmarks of a foot as independent 3D points -- §4.1, §4.3 and
the §28.3 landmark test list of research_foot_last_pose_fit_technical_report_
for_claude.md.

This replaces `scm_parser_service._ball_line_mm`, which reduced the ball line
to a single scalar Y offset from the heel. §4.3 forbids that: MTH1 and MTH5
are separate 3D points, generally with y1 != y5 and z1 != z5, and the ball line
is an oblique spatial segment, not a cross-section at one Y. On the real Nikita
foot the two landmarks sit 36.4mm apart along the length -- the entire
obliquity of the ball line, discarded by averaging them into one number.

Nothing here infers bone positions: these are surface landmarks only, each
reported with its own confidence so a downstream stage can refuse to run on a
weak detection (§28.3: "низкая confidence блокирует автоматический pose
solve") instead of silently trusting it.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh

# The two heads need different search rules, because the foot's outline gives
# them different signatures (measured on the real Nikita scan):
#
#   lateral edge: a clean peak -- protrusion grows to a maximum at ~63% of
#     length and then recedes as the outline turns in toward the little toe.
#     argmax finds MTH5 directly.
#   medial edge: NO peak at the ball. It grows steadily from the arch and keeps
#     growing past the ball all the way to the hallux (55.1mm at 90% vs 52.5mm
#     at 73%), so a plain argmax lands on the big toe, not on MTH1. What marks
#     MTH1 is the knee where the growth stops: +2.8mm over 63->73%, then only
#     +0.5mm over 73->83%. So MTH1 is taken as the *onset* of that plateau.
_MTH5_ZONE_FRACTION = (0.52, 0.75)
_MTH1_ZONE_FRACTION = (0.55, 0.85)
# The medial edge counts as "on the plateau" once it is within this of the
# plateau level (itself a high percentile of the curve, not its raw max).
_PLATEAU_TOLERANCE_MM = 1.0
_PLATEAU_PERCENTILE = 95.0
_N_LENGTH_BINS = 120
_MIN_POINTS_PER_BIN = 5
# Medial/lateral extremes are read as percentiles, not raw min/max, so a single
# spike on the scan cannot define a landmark.
_EDGE_PERCENTILE = 1.0
# Landmarks are read from the tread band only: above this height the ankle
# bones (malleoli) bulge past the footprint and would be mistaken for the
# metatarsal heads -- the same reasoning as FOOTPRINT_HEIGHT_MM in
# scm_parser_service.py, which found a spurious 2-5mm width bulge without it.
_TREAD_HEIGHT_MM = 30.0
_HEEL_ZONE_FRACTION = 0.18


@dataclass
class Landmark:
    name: str
    position: np.ndarray      # (3,) mm, in the mesh's own frame
    confidence: float
    method: str

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            # 0.1mm is already finer than any landmark is actually resolved
            # (§26.18 forbids advertising hundredths of a millimetre when the
            # landmark itself is uncertain by millimetres).
            "position_mm": [round(float(c), 1) for c in self.position],
            "confidence": round(self.confidence, 3),
            "method": self.method,
        }


@dataclass
class FootLandmarks:
    pternion: Landmark | None            # most posterior point of the heel
    plantar_heel_center: Landmark | None
    mth1: Landmark | None                # medial (first) metatarsal head
    mth5: Landmark | None                # lateral (fifth) metatarsal head
    longest_toe_tip: Landmark | None
    warnings: list[str]

    @property
    def ball_center(self) -> np.ndarray | None:
        if self.mth1 is None or self.mth5 is None:
            return None
        return (self.mth1.position + self.mth5.position) / 2.0

    @property
    def ball_axis(self) -> np.ndarray | None:
        """MTH1 -> MTH5 as a real 3D segment (§4.3), not a Y coordinate."""
        if self.mth1 is None or self.mth5 is None:
            return None
        return self.mth5.position - self.mth1.position

    def ball_obliquity_mm(self) -> float | None:
        """How far apart the two heads sit *along the length* -- the quantity a
        single `ball_y` throws away."""
        axis = self.ball_axis
        return None if axis is None else abs(float(axis[1]))

    @property
    def confidence(self) -> float:
        parts = [lm.confidence for lm in
                 (self.pternion, self.plantar_heel_center, self.mth1, self.mth5)
                 if lm is not None]
        if len(parts) < 4:
            return 0.0
        return float(np.min(parts))

    def as_dict(self) -> dict:
        return {
            "pternion": self.pternion.as_dict() if self.pternion else None,
            "plantar_heel_center": self.plantar_heel_center.as_dict() if self.plantar_heel_center else None,
            "mth1": self.mth1.as_dict() if self.mth1 else None,
            "mth5": self.mth5.as_dict() if self.mth5 else None,
            "longest_toe_tip": self.longest_toe_tip.as_dict() if self.longest_toe_tip else None,
            "ball_obliquity_mm": (round(self.ball_obliquity_mm(), 1)
                                  if self.ball_obliquity_mm() is not None else None),
            "confidence": round(self.confidence, 3),
            "warnings": list(self.warnings),
        }


def _bin_edges(y: np.ndarray, frac_lo: float, frac_hi: float) -> tuple[np.ndarray, float, float]:
    y_min, y_max = float(y.min()), float(y.max())
    length = y_max - y_min
    lo = y_min + frac_lo * length
    hi = y_min + frac_hi * length
    return np.linspace(lo, hi, _N_LENGTH_BINS + 1), y_min, length


def _find_metatarsal_heads(v: np.ndarray, medial_sign: float) -> tuple[Landmark | None, Landmark | None, list[str]]:
    """Medial and lateral metatarsal heads, each located independently as the
    point where its own side of the foot bulges out furthest within the ball
    zone. They are NOT constrained to share a Y -- that constraint is exactly
    what §4.3 prohibits.

    `medial_sign` is +1 when +X is the medial side, -1 when it is lateral.
    """
    warnings: list[str] = []
    y, x, z = v[:, 1], v[:, 0], v[:, 2]
    tread = z <= _TREAD_HEIGHT_MM
    if tread.sum() < _MIN_POINTS_PER_BIN * 10:
        return None, None, ["tread_band_too_sparse"]

    def edge_curve(zone: tuple[float, float]) -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
        """Per-band medial protrusion (signed so larger = more medial), the
        band centres, and a representative 3D point on each band's edge."""
        edges, _y_min, _length = _bin_edges(y, *zone)
        centres, values, points = [], [], []
        for lo, hi in zip(edges[:-1], edges[1:]):
            band = tread & (y >= lo) & (y < hi)
            if band.sum() < _MIN_POINTS_PER_BIN:
                continue
            xs = x[band] * medial_sign
            med_edge = float(np.percentile(xs, 100 - _EDGE_PERCENTILE))
            pts = v[band][xs >= med_edge - 0.5]
            if not len(pts):
                continue
            centres.append((lo + hi) / 2.0)
            values.append(med_edge)
            points.append(pts.mean(axis=0))
        return np.array(centres), np.array(values), points

    length = float(y.max() - y.min())

    # --- MTH1: onset of the medial plateau ---------------------------------
    m_centres, m_values, m_points = edge_curve(_MTH1_ZONE_FRACTION)
    mth1 = None
    if len(m_values) >= 4:
        plateau = float(np.percentile(m_values, _PLATEAU_PERCENTILE))
        on_plateau = np.where(m_values >= plateau - _PLATEAU_TOLERANCE_MM)[0]
        if len(on_plateau):
            i = int(on_plateau[0])
            mth1 = Landmark("MTH1", m_points[i], 1.0, "medial_plateau_onset")
            # How sharply the plateau begins is how well-defined the landmark
            # is: a knee that takes a long stretch to develop is a weak read.
            span = float(m_centres[-1] - m_centres[0]) or 1.0
            sharpness = 1.0 - (m_centres[i] - m_centres[0]) / span
            mth1.confidence = float(np.clip(sharpness * 1.4, 0.2, 1.0))

    # --- MTH5: true lateral peak -------------------------------------------
    l_centres, l_values, l_points = edge_curve(_MTH5_ZONE_FRACTION)
    mth5 = None
    if len(l_values) >= 4:
        # `edge_curve` reports medial protrusion; the lateral extreme is its
        # minimum, so recompute the lateral edge explicitly.
        edges, _ym, _L = _bin_edges(y, *_MTH5_ZONE_FRACTION)
        centres, values, points = [], [], []
        for lo, hi in zip(edges[:-1], edges[1:]):
            band = tread & (y >= lo) & (y < hi)
            if band.sum() < _MIN_POINTS_PER_BIN:
                continue
            xs = x[band] * medial_sign
            lat_edge = float(np.percentile(xs, _EDGE_PERCENTILE))
            pts = v[band][xs <= lat_edge + 0.5]
            if not len(pts):
                continue
            centres.append((lo + hi) / 2.0)
            values.append(lat_edge)
            points.append(pts.mean(axis=0))
        if len(values) >= 4:
            values = np.array(values)
            i = int(np.argmin(values))  # most laterally protruding band
            mth5 = Landmark("MTH5", points[i], 1.0, "lateral_peak")
            y_lo, y_hi = centres[0], centres[-1]
            margin = min(abs(centres[i] - y_lo), abs(centres[i] - y_hi))
            mth5.confidence = float(np.clip(margin / (0.05 * length), 0.2, 1.0))
            if margin < 0.02 * length:
                warnings.append("mth5_at_search_zone_edge")

    if mth1 is None or mth5 is None:
        warnings.append("ball_landmarks_not_found")
    return mth1, mth5, warnings


def detect_foot_landmarks(mesh: trimesh.Trimesh, side: str | None = None) -> FootLandmarks:
    """Surface landmarks of a foot mesh, each independent and each with its own
    confidence. `side` ("left"/"right") tells which X direction is medial; when
    unknown the medial side is guessed from where the forefoot is widest, and
    the guess is flagged."""
    warnings: list[str] = []
    v = np.asarray(mesh.vertices, dtype=float)
    if len(v) < 100:
        return FootLandmarks(None, None, None, None, None, ["mesh_too_sparse"])

    y, z = v[:, 1], v[:, 2]
    y_min, y_max = float(y.min()), float(y.max())
    length = y_max - y_min

    # pternion: the most posterior point (§4.1), taken as the centroid of the
    # rearmost sliver so it is a point on the surface, not one extreme vertex.
    rear = y <= y_min + max(1.0, 0.005 * length)
    pternion = Landmark("PTERNION", v[rear].mean(axis=0), 1.0, "rearmost_sliver_centroid") \
        if rear.sum() >= 3 else None

    # plantar heel centre: centroid of the low, rear contact region
    heel_zone = (y <= y_min + _HEEL_ZONE_FRACTION * length)
    low = z <= (float(z.min()) + 5.0)
    plantar = heel_zone & low
    plantar_heel = Landmark("PLANTAR_HEEL_CENTER", v[plantar].mean(axis=0), 1.0,
                            "low_rear_region_centroid") if plantar.sum() >= 10 else None
    if plantar_heel is None:
        warnings.append("plantar_heel_center_not_found")

    if side in ("left", "right"):
        # This codebase's convention (scm_parser_service.extract_profile):
        # +X is medial for a left foot.
        medial_sign = 1.0 if side == "left" else -1.0
    else:
        medial_sign = 1.0
        warnings.append("foot_side_unknown_medial_direction_assumed")

    mth1, mth5, ball_warnings = _find_metatarsal_heads(v, medial_sign)
    warnings.extend(ball_warnings)

    front = y >= y_max - max(1.0, 0.005 * length)
    longest_toe = Landmark("LONGEST_TOE_TIP", v[front].mean(axis=0), 1.0,
                           "frontmost_sliver_centroid") if front.sum() >= 3 else None

    landmarks = FootLandmarks(pternion, plantar_heel, mth1, mth5, longest_toe, warnings)
    warnings.extend(_sanity_check(landmarks, y_min, length))
    return landmarks


def _sanity_check(lm: FootLandmarks, y_min: float, length: float) -> list[str]:
    """§28.3: the checks that must fail loudly rather than produce a confident
    wrong answer."""
    problems: list[str] = []
    if lm.mth1 is not None and lm.mth5 is not None:
        for head in (lm.mth1, lm.mth5):
            frac = (head.position[1] - y_min) / length
            if frac < 0.35:
                problems.append(f"{head.name.lower()}_inside_heel_region")
            if frac > 0.95:
                problems.append(f"{head.name.lower()}_at_toe_tip")
        if lm.ball_obliquity_mm() is not None and lm.ball_obliquity_mm() > 0.35 * length:
            problems.append("ball_axis_implausibly_oblique")
    if lm.pternion is not None and lm.plantar_heel_center is not None:
        if np.allclose(lm.pternion.position, lm.plantar_heel_center.position, atol=1e-6):
            problems.append("pternion_coincides_with_plantar_heel")
    return problems
