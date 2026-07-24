"""Heel height / toe spring / ball line measurement for a last — stage 1 of
heel_toe_measurement_foot_deformation_visualization_spec.md.

Key finding from checking this against the real Prada 43 last during
development (not asserted in the committed test suite, which is synthetic
only — see tests/test_last_bottom_profile.py's docstring): the spec's own
"technical heel height" (23.104mm) and toe spring tip (36.268mm) are the Z of
the *exact* extreme vertex (min/max Y) — not a percentile read over a Y-band
near that end. A banded/percentile read at the very tip picks up the heel
breast's near-vertical back wall (which touches down anywhere from a few mm
to over 30mm depending on where exactly in that band it's sampled) rather
than the tip point itself. The spec's own §7.1 "naive" formula
(`heel_point = vertex_with_min_y`) is what actually reproduces its own
validation numbers — confirmed by reading that literal vertex on the real
file and matching to 3 decimal places. The more "robust" region-based reads
(§7.2/§7.3: heel_height_at_2/5_percent, heel_seat_mean_height) are kept as
*separate* fields precisely because the spec anticipates them differing from
the endpoint value (§7.3: "различать высоту крайней точки и высоту рабочей
пяточной площадки") — on this real last they differ by roughly 10mm, which
is exactly that distinction doing its job, not a bug.
"""
from __future__ import annotations

import numpy as np
import trimesh

from app.services.last_bottom_profile import (
    GroundPlane,
    extract_bottom_profile,
    find_ground_plane,
    profile_z_at_y,
)
from app.services.scm_parser_service import _ball_line_mm

_REAR_REGION_MAX_U = 0.03
_TOE_SPRING_FRACTIONS = (0.80, 0.85, 0.90, 0.95)

# toe_spring_start detection (spec §8.3): smoothed dZ/dY must exceed this
# slope (mm rise per mm length) and stay elevated for at least this long.
_TOE_RISE_MIN_SLOPE = 0.12
_TOE_RISE_SUSTAIN_MM = 10.0


def _region_mean_height(profile: list[dict], y_min: float, length: float,
                         u_lo: float, u_hi: float, ground_z: float) -> float | None:
    ys = np.array([p["y"] for p in profile])
    zs = np.array([p["z"] for p in profile])
    u = (ys - y_min) / length
    mask = (u >= u_lo) & (u <= u_hi)
    if not mask.any():
        return None
    return float(np.mean(zs[mask]) - ground_z)


def _find_toe_spring_start_y(profile: list[dict], search_from_y: float) -> float | None:
    ys = np.array([p["y"] for p in profile])
    zs = np.array([p["z"] for p in profile])
    order = np.argsort(ys)
    ys, zs = ys[order], zs[order]
    mask = ys >= search_from_y
    if mask.sum() < 4:
        return None
    ys_m, zs_m = ys[mask], zs[mask]
    dy = np.diff(ys_m)
    dz = np.diff(zs_m)
    with np.errstate(divide="ignore", invalid="ignore"):
        slope = np.where(dy > 1e-6, dz / dy, 0.0)
    candidate_ys = ys_m[:-1]

    for i, y0 in enumerate(candidate_ys):
        if slope[i] <= _TOE_RISE_MIN_SLOPE:
            continue
        sustain_mask = (candidate_ys >= y0) & (candidate_ys <= y0 + _TOE_RISE_SUSTAIN_MM)
        if sustain_mask.sum() >= 2 and np.all(slope[sustain_mask] > _TOE_RISE_MIN_SLOPE * 0.5):
            return float(y0)
    return None


def measure_heel_toe(mesh: trimesh.Trimesh, profile: list[dict], ground_z: float) -> dict:
    y = mesh.vertices[:, 1]
    z = mesh.vertices[:, 2]
    y_min, y_max = float(y.min()), float(y.max())
    length = y_max - y_min

    heel_height_endpoint = float(z[np.argmin(y)]) - ground_z
    toe_spring_tip = float(z[np.argmax(y)]) - ground_z

    heel_height_at_2_percent = profile_z_at_y(profile, y_min + 0.02 * length)
    heel_height_at_5_percent = profile_z_at_y(profile, y_min + 0.05 * length)
    if heel_height_at_2_percent is not None:
        heel_height_at_2_percent -= ground_z
    if heel_height_at_5_percent is not None:
        heel_height_at_5_percent -= ground_z
    heel_seat_mean_height = _region_mean_height(profile, y_min, length, 0.0, _REAR_REGION_MAX_U, ground_z)

    toe_spring_profile = {}
    for frac in _TOE_SPRING_FRACTIONS:
        z_at = profile_z_at_y(profile, y_min + frac * length)
        toe_spring_profile[f"toe_spring_{int(frac * 100)}"] = (
            round(z_at - ground_z, 2) if z_at is not None else None
        )

    return {
        "heel_height_endpoint_mm": round(heel_height_endpoint, 3),
        "heel_height_at_2_percent_mm": round(heel_height_at_2_percent, 2) if heel_height_at_2_percent is not None else None,
        "heel_height_at_5_percent_mm": round(heel_height_at_5_percent, 2) if heel_height_at_5_percent is not None else None,
        "heel_seat_mean_height_mm": round(heel_seat_mean_height, 2) if heel_seat_mean_height is not None else None,
        "toe_spring_tip_mm": round(toe_spring_tip, 3),
        **toe_spring_profile,
        "toe_spring_start_y_mm": None,  # filled in by measure_last_pose once ball_line is known
        "y_min_mm": y_min,
        "y_max_mm": y_max,
        "length_mm": length,
    }


def measure_last_pose(last_mesh: trimesh.Trimesh) -> dict:
    """Full stage-1 measurement: ground plane, bottom profile, heel/toe
    heights, ball line, confidence. Shape matches the spec's §22.1 JSON."""
    ground_plane = find_ground_plane(last_mesh)
    profile = extract_bottom_profile(last_mesh)
    heel_toe = measure_heel_toe(last_mesh, profile, ground_plane.ground_z)

    v = last_mesh.vertices
    # _ball_line_mm returns an offset from the heel (y_min), not an absolute
    # Y coordinate -- see its own docstring in scm_parser_service.py.
    ball_line_offset = _ball_line_mm(v[:, 0], v[:, 1])
    ball_line_method = "automatic_geometry" if ball_line_offset is not None else "unavailable"
    ball_line_y = (heel_toe["y_min_mm"] + ball_line_offset) if ball_line_offset is not None else None

    search_from_y = ball_line_y if ball_line_y is not None else heel_toe["y_min_mm"] + heel_toe["length_mm"] * 0.5
    toe_spring_start_y = _find_toe_spring_start_y(profile, search_from_y)
    heel_toe["toe_spring_start_y_mm"] = round(toe_spring_start_y, 1) if toe_spring_start_y is not None else None

    # Confidence: ground-plane fit quality is the dominant factor (a bad
    # ground plane invalidates every height measurement downstream); ball
    # line detection failing is a secondary penalty since the deformation
    # stage still needs it as a pivot.
    confidence = ground_plane.confidence
    if ball_line_y is None:
        confidence *= 0.5

    return {
        "heel_height_mm": heel_toe["heel_height_endpoint_mm"],
        "toe_spring_tip_mm": heel_toe["toe_spring_tip_mm"],
        "toe_spring_start_y_mm": heel_toe["toe_spring_start_y_mm"],
        "ball_line_y_mm": round(ball_line_y, 2) if ball_line_y is not None else None,
        "ball_line_method": ball_line_method,
        "ground_plane": ground_plane.as_dict(),
        "bottom_profile": profile,
        "heel_toe_detail": heel_toe,
        "method": "automatic_geometry",
        "confidence": round(confidence, 3),
    }
