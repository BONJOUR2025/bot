"""Ground plane + longitudinal bottom profile extraction — shared groundwork
for automatic last-pose measurement (heel_toe_measurement_foot_deformation_
visualization_spec.md, "Этап 1"). Works on any mesh in this codebase's
canonical coordinate convention (X=width, Y=length from heel, Z=height above
the ground) — both a last (to measure its own sole curve) and a foot (its
plantar centerline is one of the anchors the deformation stage needs).

Deliberately not literal RANSAC (§6.2 of the spec): every real last/foot scan
this session has touched sits with a flat, already-clean support region at
Z=0 (confirmed repeatedly — mesh3d_service.py, last_registration_service.py).
A full iterative RANSAC consensus loop solves a problem this data doesn't
actually have. Instead: take a robust "core" of low-Z points (trim the
extreme heel/front tips, which can genuinely slope away from the flat
support per the spec's own warning), fit a plane by SVD, and report the fit
quality (angle to vertical, RMS residual) so a badly-behaved scan is flagged
rather than silently trusted — the same honesty the spec asks for without
needing a heavier algorithm this dataset doesn't require.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh
from scipy.signal import savgol_filter

_LOW_Z_PERCENTILE = 2.0        # bottom N% of vertices by Z as hole "ground candidates"
_CORE_Y_TRIM_LO, _CORE_Y_TRIM_HI = 10.0, 90.0  # trim extreme heel/toe tips (percentile of Y within the low-Z set)
_MIN_CORE_POINTS = 20
_GOOD_ANGLE_DEG = 3.0          # plane closer to vertical than this -> full confidence
_BAD_ANGLE_DEG = 15.0          # plane tilted more than this -> ~zero confidence
_GOOD_RMS_MM = 0.5
_BAD_RMS_MM = 3.0

_PROFILE_STEP_MM = 1.0
_PROFILE_LOW_PERCENTILE = 2.0  # P1-P3 per the spec (§5.2) -- robust "bottom of bin", not bare min
_MIN_POINTS_PER_BIN = 3
_SAVGOL_WINDOW = 9
_SAVGOL_POLYORDER = 2


@dataclass
class GroundPlane:
    ground_z: float
    normal: np.ndarray
    angle_to_vertical_deg: float
    rms_error_mm: float
    n_points: int
    confidence: float

    def as_dict(self) -> dict:
        return {
            "ground_z": round(self.ground_z, 3),
            "normal": [round(float(v), 4) for v in self.normal],
            "angle_to_vertical_deg": round(self.angle_to_vertical_deg, 2),
            "rms_error_mm": round(self.rms_error_mm, 3),
            "n_points": self.n_points,
            "confidence": round(self.confidence, 3),
        }


def _linear_confidence(value: float, good: float, bad: float) -> float:
    """1.0 at/below `good`, 0.0 at/above `bad`, linear between."""
    if value <= good:
        return 1.0
    if value >= bad:
        return 0.0
    return float(1.0 - (value - good) / (bad - good))


def find_ground_plane(mesh: trimesh.Trimesh) -> GroundPlane:
    z = mesh.vertices[:, 2]
    low_mask = z <= np.percentile(z, _LOW_Z_PERCENTILE)
    low_pts = mesh.vertices[low_mask]

    y = low_pts[:, 1]
    y_lo, y_hi = np.percentile(y, [_CORE_Y_TRIM_LO, _CORE_Y_TRIM_HI])
    core_mask = (y >= y_lo) & (y <= y_hi)
    core = low_pts[core_mask]
    if len(core) < _MIN_CORE_POINTS:
        core = low_pts  # too few points after trimming -- fall back to the untrimmed set

    centroid = core.mean(axis=0)
    _, _, vt = np.linalg.svd(core - centroid)
    normal = vt[-1]
    if normal[2] < 0:
        normal = -normal
    normal = normal / np.linalg.norm(normal)

    angle_deg = float(np.degrees(np.arccos(np.clip(normal[2], -1.0, 1.0))))
    offset = -normal @ centroid
    residuals = core @ normal + offset
    rms_error = float(np.sqrt(np.mean(residuals ** 2)))

    confidence = _linear_confidence(angle_deg, _GOOD_ANGLE_DEG, _BAD_ANGLE_DEG) * \
        _linear_confidence(rms_error, _GOOD_RMS_MM, _BAD_RMS_MM)

    return GroundPlane(
        ground_z=float(np.median(core[:, 2])),
        normal=normal, angle_to_vertical_deg=angle_deg, rms_error_mm=rms_error,
        n_points=len(core), confidence=confidence,
    )


def extract_bottom_profile(mesh: trimesh.Trimesh, step_mm: float = _PROFILE_STEP_MM) -> list[dict]:
    """Longitudinal Z_bottom(Y) profile — the spec's own §5.2 MVP algorithm
    (bin by Y, robust low percentile per bin, smooth), used both for a
    last's sole curve and a foot's plantar centerline."""
    y = mesh.vertices[:, 1]
    z = mesh.vertices[:, 2]
    y_min, y_max = float(y.min()), float(y.max())
    bins = np.arange(y_min, y_max + step_mm, step_mm)

    profile: list[dict] = []
    for y0, y1 in zip(bins[:-1], bins[1:]):
        mask = (y >= y0) & (y < y1)
        if mask.sum() < _MIN_POINTS_PER_BIN:
            continue
        z_bottom = float(np.percentile(z[mask], _PROFILE_LOW_PERCENTILE))
        profile.append({"y": float((y0 + y1) / 2.0), "z": z_bottom})

    return _smooth_profile(profile)


def _smooth_profile(profile: list[dict]) -> list[dict]:
    if len(profile) < _SAVGOL_WINDOW:
        return profile
    z_vals = np.array([p["z"] for p in profile])
    window = _SAVGOL_WINDOW if _SAVGOL_WINDOW % 2 == 1 else _SAVGOL_WINDOW + 1
    window = min(window, len(z_vals) if len(z_vals) % 2 == 1 else len(z_vals) - 1)
    if window <= _SAVGOL_POLYORDER:
        return profile
    smoothed = savgol_filter(z_vals, window_length=window, polyorder=_SAVGOL_POLYORDER)
    return [{"y": p["y"], "z": float(s)} for p, s in zip(profile, smoothed)]


def profile_z_at_y(profile: list[dict], y_query: float) -> float | None:
    """Linear interpolation of the profile at an arbitrary Y (clamped to the
    profile's own range) — used throughout the deformation stage to read
    Z_bottom at any Y, not just the sampled bin centers."""
    if not profile:
        return None
    ys = np.array([p["y"] for p in profile])
    zs = np.array([p["z"] for p in profile])
    order = np.argsort(ys)
    return float(np.interp(y_query, ys[order], zs[order]))
