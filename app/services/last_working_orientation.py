"""Working orientation of a last, and its *effective* heel elevation --
§6 and §10.2 of research_foot_last_pose_fit_technical_report_for_claude.md.

This replaces the heel-height measurement in last_pose_measurements.py, which
took the Z of the last's rearmost vertex. That number is not a heel elevation
at all: the rearmost vertex sits on the curved back wall of the heel, so its Z
reports how tall that wall happens to be where it is sampled. §6.2 forbids it
by name ("Не использовать как высоту пятки: Z самой задней вершины").

Confirmed on the real Prada 43 last: its bottom profile touches the support
plane in two clusters -- the heel seat (0-15% of length) and the ball tread
(50-70%), *both* at Z~0. The last is effectively flat, yet the rearmost-vertex
reading claimed 22.7mm, which the pose stage turned into a spurious ~6.9 deg
heel rotation applied to every foot.

What a heel elevation actually is (§10.2) is the height difference between the
two surfaces the foot is supported on:

    effective_heel_elevation = Z_heel_support - Z_ball_support

Both are read off the last's own bottom (sole) profile as seated *patches*,
never as single extreme vertices, so one stray vertex cannot move the result --
which is what §6.3's stability checks ask us to guarantee and report.

Note the support patches are deliberately not defined as "what touches the
plane the last rests on": a genuinely heeled last has its heel seat raised by
design, so that surface never contacts the table at all, and only the ball
tread and the bottom of the heel block do. Reading both seats off the bottom
profile works for a flat and a heeled last alike.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh

from app.services.last_bottom_profile import extract_bottom_profile, find_ground_plane

# The two support patches are located on the last's own *bottom profile* (its
# sole/feather surface), not by what happens to touch a table. That distinction
# matters for a genuinely heeled last: its heel seat is raised by design, so it
# never contacts the plane the last rests on -- only the ball tread and the
# bottom of the heel block do. §10.2 defines the elevation between the surfaces
# the foot is supported on, which is what the bottom profile describes.
_HEEL_WINDOW = (0.03, 0.18)   # rear window: the heel seat itself, before the waist
_BALL_WINDOW = (0.45, 0.75)   # forward window: the ball tread
# The two patches have to be read differently. The ball tread is the lowest
# part of its window by definition (it is what the last stands on), so a low
# percentile finds it. The heel seat is a plateau whose own level is what
# matters -- on a heeled last the profile *descends* from it toward the waist,
# so a low percentile there would slide down the waist and under-report the
# elevation (it measured 20mm on a 25mm synthetic heel before this split).
_BALL_PERCENTILE = 15.0
_SEAT_BAND_MM = 2.0           # samples within this of the level form the patch
_MIN_CLUSTER_POINTS = 3

# §6.3: re-measuring without the most extreme 1% of contact points must not
# move the elevation by more than this, or the reading rests on outliers.
_OUTLIER_TRIM_FRACTION = 0.01
_MAX_OUTLIER_SHIFT_MM = 1.0


@dataclass
class SupportCluster:
    """One contact patch between the last and its support plane."""
    y_min: float
    y_max: float
    height_mm: float          # robust height of the patch above the support plane
    n_points: int
    fraction_range: tuple[float, float]

    def as_dict(self) -> dict:
        return {
            "y_min_mm": round(self.y_min, 1),
            "y_max_mm": round(self.y_max, 1),
            "height_mm": round(self.height_mm, 2),
            "n_points": self.n_points,
            "length_fraction": [round(self.fraction_range[0], 3), round(self.fraction_range[1], 3)],
        }


@dataclass
class WorkingOrientation:
    effective_heel_elevation_mm: float
    heel_support: SupportCluster | None
    ball_support: SupportCluster | None
    ground_z: float
    orientation_confidence: float
    warnings: list[str] = field(default_factory=list)
    method: str = "support_clusters_v1"

    def as_dict(self) -> dict:
        return {
            "effective_heel_elevation_mm": round(self.effective_heel_elevation_mm, 2),
            "heel_support": self.heel_support.as_dict() if self.heel_support else None,
            "ball_support": self.ball_support.as_dict() if self.ball_support else None,
            "ground_z": round(self.ground_z, 3),
            "orientation_confidence": round(self.orientation_confidence, 3),
            "warnings": list(self.warnings),
            "method": self.method,
        }


def _seat_in_window(fracs: np.ndarray, zs: np.ndarray, ys: np.ndarray,
                    window: tuple[float, float], mode: str = "low") -> SupportCluster | None:
    """The support patch inside a length window, read from the bottom profile.
    `mode="low"` takes the lowest part (the ball tread); `mode="plateau"` takes
    the window's own representative level (the heel seat) -- see the constants
    above for why the two cannot share one rule."""
    sel = (fracs >= window[0]) & (fracs <= window[1])
    if sel.sum() < _MIN_CLUSTER_POINTS:
        return None
    z_win, f_win, y_win = zs[sel], fracs[sel], ys[sel]
    seat_level = float(np.median(z_win) if mode == "plateau"
                       else np.percentile(z_win, _BALL_PERCENTILE))
    patch = z_win <= seat_level + _SEAT_BAND_MM
    if patch.sum() < _MIN_CLUSTER_POINTS:
        patch = z_win <= seat_level + _SEAT_BAND_MM * 2
    if patch.sum() < _MIN_CLUSTER_POINTS:
        return None
    return SupportCluster(
        y_min=float(y_win[patch].min()), y_max=float(y_win[patch].max()),
        height_mm=float(np.median(z_win[patch])),
        n_points=int(patch.sum()),
        fraction_range=(float(f_win[patch].min()), float(f_win[patch].max())),
    )


def estimate_working_orientation(
    last_mesh: trimesh.Trimesh,
    maker_heel_height_mm: float | None = None,
    maker_toe_spring_mm: float | None = None,
) -> WorkingOrientation:
    """Effective heel elevation of `last_mesh` plus a confidence in it.

    `maker_heel_height_mm` is the manufacturer's own figure (§6.2 prefers it
    over anything inferred); when given it is reported as-is and the measured
    clusters only serve as a cross-check.
    """
    warnings: list[str] = []
    plane = find_ground_plane(last_mesh)
    v = last_mesh.vertices
    y = v[:, 1]
    y_min, y_max = float(y.min()), float(y.max())
    length_mm = y_max - y_min
    if length_mm <= 0:
        return WorkingOrientation(0.0, None, None, plane.ground_z, 0.0,
                                  ["degenerate_length"])

    profile = extract_bottom_profile(last_mesh)
    if len(profile) < 8:
        warnings.append("bottom_profile_too_sparse")
        return WorkingOrientation(0.0, None, None, plane.ground_z, 0.0, warnings)
    p_y = np.array([p["y"] for p in profile])
    p_z = np.array([p["z"] for p in profile]) - plane.ground_z
    p_f = (p_y - y_min) / length_mm

    heel = _seat_in_window(p_f, p_z, p_y, _HEEL_WINDOW, mode="plateau")
    ball = _seat_in_window(p_f, p_z, p_y, _BALL_WINDOW, mode="low")

    if heel is None or ball is None:
        warnings.append("support_clusters_not_identified")
        # No trustworthy support pair -- report a zero elevation with zero
        # confidence rather than inventing one from extreme vertices, which is
        # the failure this module exists to prevent.
        return WorkingOrientation(0.0, heel, ball, plane.ground_z, 0.0, warnings)

    if heel.fraction_range[0] >= ball.fraction_range[0]:
        warnings.append("heel_support_not_behind_ball_support")  # §6.3

    elevation = heel.height_mm - ball.height_mm

    # §6.3 stability: re-measure without the most extreme 1% of profile samples
    # -- if that moves the answer, it rested on outliers rather than on a seat.
    trimmed_elevation = elevation
    if len(p_z) > 20:
        lo, hi = np.percentile(p_z, [_OUTLIER_TRIM_FRACTION * 100,
                                      100 - _OUTLIER_TRIM_FRACTION * 100])
        keep = (p_z >= lo) & (p_z <= hi)
        t_heel = _seat_in_window(p_f[keep], p_z[keep], p_y[keep], _HEEL_WINDOW, mode="plateau")
        t_ball = _seat_in_window(p_f[keep], p_z[keep], p_y[keep], _BALL_WINDOW, mode="low")
        if t_heel is not None and t_ball is not None:
            trimmed_elevation = t_heel.height_mm - t_ball.height_mm
    outlier_shift = abs(trimmed_elevation - elevation)
    if outlier_shift > _MAX_OUTLIER_SHIFT_MM:
        warnings.append("elevation_depends_on_outliers")

    confidence = plane.confidence
    confidence *= float(np.clip(1.0 - outlier_shift / _MAX_OUTLIER_SHIFT_MM, 0.0, 1.0))
    if "heel_support_not_behind_ball_support" in warnings:
        confidence *= 0.2

    if maker_heel_height_mm is not None:
        # §6.2: the maker's figure wins; the measurement becomes a cross-check,
        # and a large disagreement is surfaced rather than silently overridden.
        if abs(maker_heel_height_mm - elevation) > 5.0:
            warnings.append("maker_heel_height_disagrees_with_measurement")
        elevation = float(maker_heel_height_mm)
        confidence = max(confidence, 0.9)

    return WorkingOrientation(
        effective_heel_elevation_mm=float(elevation),
        heel_support=heel, ball_support=ball,
        ground_z=plane.ground_z,
        orientation_confidence=float(np.clip(confidence, 0.0, 1.0)),
        warnings=warnings,
    )
