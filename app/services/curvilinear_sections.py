"""Cross-sections taken orthogonally to the object's own centreline -- §5.4 of
research_foot_last_pose_fit_technical_report_for_claude.md.

`mesh3d_service.exact_section` cuts with planes at Y = constant. That is fine
for a flat scan, but §26.13 forbids it once a pose has been applied: after the
heel is rotated up the foot's own axis no longer runs along Y, so a Y-constant
plane slices the geometry obliquely and every width/height/area it reports is
measured across the wrong direction.

§5.4 asks for a curvilinear frame instead: arc length `s` along the functional
centreline, with sections in planes orthogonal to the tangent `t(s)`. That is
what this module builds. The centreline runs through the *centroids* of the
volume (not along the sole), so it follows the object's own bending rather than
a fixed world axis, and sections stay perpendicular to it however the object is
posed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh
from scipy.signal import savgol_filter

_DEFAULT_CENTERLINE_SAMPLES = 60
_MIN_POINTS_PER_BIN = 8
_SMOOTH_WINDOW = 9
_SMOOTH_POLYORDER = 2


@dataclass
class CurvilinearSection:
    s: float                  # arc length along the centreline, mm from the heel
    s_fraction: float         # 0..1 along the centreline
    center: np.ndarray        # (3,) point on the centreline
    tangent: np.ndarray       # (3,) unit, section plane normal
    width_mm: float           # extent across the section (medial-lateral)
    height_mm: float          # extent up the section
    area_mm2: float
    perimeter_mm: float       # section girth

    def as_dict(self) -> dict:
        return {
            "s_mm": round(self.s, 1),
            "s_fraction": round(self.s_fraction, 3),
            "center_mm": [round(float(c), 1) for c in self.center],
            "width_mm": round(self.width_mm, 1),
            "height_mm": round(self.height_mm, 1),
            "area_mm2": round(self.area_mm2, 1),
            "perimeter_mm": round(self.perimeter_mm, 1),
        }


@dataclass
class Centerline:
    points: np.ndarray        # (N, 3) smoothed centroid path
    tangents: np.ndarray      # (N, 3) unit tangents
    arc_length: np.ndarray    # (N,) cumulative arc length, mm

    @property
    def total_length_mm(self) -> float:
        return float(self.arc_length[-1]) if len(self.arc_length) else 0.0

    def sample(self, s: float) -> tuple[np.ndarray, np.ndarray]:
        """Point and tangent at arc length `s` (clamped to the curve)."""
        s = float(np.clip(s, self.arc_length[0], self.arc_length[-1]))
        point = np.array([np.interp(s, self.arc_length, self.points[:, k]) for k in range(3)])
        tangent = np.array([np.interp(s, self.arc_length, self.tangents[:, k]) for k in range(3)])
        norm = np.linalg.norm(tangent)
        return point, (tangent / norm if norm > 1e-9 else np.array([0.0, 1.0, 0.0]))


def _principal_axis(v: np.ndarray) -> np.ndarray:
    """The object's own long axis (first principal component).

    Binning along world Y instead would defeat the entire purpose of this
    module: measured on the real Nikita foot, rotating it rigidly by 20 deg --
    which cannot change any true cross-section -- moved the reported section
    area by +21% when the centreline was built from Y bins, because those bins
    then slice the rotated object obliquely. A principal axis rotates with the
    object, so the centreline (and every section square to it) is invariant.

    Sign convention: oriented to agree with this codebase's heel->toe = +Y
    convention. A pose that turned the foot past 90 deg would flip it, which no
    heel elevation does.
    """
    centred = v - v.mean(axis=0)
    # covariance eigenvector, not SVD of the full point set: cheap and enough
    _vals, vecs = np.linalg.eigh(np.cov(centred.T))
    axis = vecs[:, -1]
    if axis[1] < 0:
        axis = -axis
    return axis / np.linalg.norm(axis)


def build_centerline(mesh: trimesh.Trimesh, n_samples: int = _DEFAULT_CENTERLINE_SAMPLES) -> Centerline | None:
    """Centroid path along the mesh's own long axis, smoothed and arc-length
    parameterised. Centroids (rather than the sole profile) so the curve tracks
    how the *body* bends, which is what a section plane must stay square to."""
    v = np.asarray(mesh.vertices, dtype=float)
    if len(v) < _MIN_POINTS_PER_BIN * 4:
        return None

    axis = _principal_axis(v)
    t = v @ axis                      # position along the object's own length
    t_min, t_max = float(t.min()), float(t.max())
    if t_max - t_min <= 0:
        return None

    edges = np.linspace(t_min, t_max, n_samples + 1)
    centroids = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        band = (t >= lo) & (t < hi)
        if band.sum() < _MIN_POINTS_PER_BIN:
            continue
        centroids.append(v[band].mean(axis=0))
    if len(centroids) < 4:
        return None
    pts = np.array(centroids)

    if len(pts) >= _SMOOTH_WINDOW:
        window = min(_SMOOTH_WINDOW if _SMOOTH_WINDOW % 2 else _SMOOTH_WINDOW + 1,
                     len(pts) if len(pts) % 2 else len(pts) - 1)
        if window > _SMOOTH_POLYORDER:
            for k in range(3):
                pts[:, k] = savgol_filter(pts[:, k], window_length=window, polyorder=_SMOOTH_POLYORDER)

    tangents = np.gradient(pts, axis=0)
    norms = np.linalg.norm(tangents, axis=1, keepdims=True)
    norms[norms < 1e-9] = 1.0
    tangents = tangents / norms

    steps = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(steps)])
    return Centerline(points=pts, tangents=tangents, arc_length=arc)


def section_at(mesh: trimesh.Trimesh, centerline: Centerline, s: float) -> CurvilinearSection | None:
    """Cut `mesh` with the plane through the centreline at arc length `s`,
    normal to the tangent there (§5.4)."""
    origin, tangent = centerline.sample(s)
    try:
        section = mesh.section(plane_origin=origin, plane_normal=tangent)
    except Exception:
        return None
    if section is None:
        return None
    try:
        planar, _transform = section.to_2D()
        polygons = planar.polygons_full
    except Exception:
        return None
    if not polygons:
        return None
    # Same convention as mesh3d_service.exact_section: several disjoint
    # contours can appear, and the largest is the real cross-section rather
    # than something to sum blindly.
    polygon = max(polygons, key=lambda p: p.area)
    coords = np.array(polygon.exterior.coords)

    # In the section's own 2D frame, decompose the extents onto the world "up"
    # direction so height stays height however the object is posed.
    world_up = np.array([0.0, 0.0, 1.0])
    up_in_plane = world_up - tangent * float(np.dot(world_up, tangent))
    if np.linalg.norm(up_in_plane) < 1e-8:
        up_in_plane = np.array([0.0, 0.0, 1.0])
    up_in_plane /= np.linalg.norm(up_in_plane)
    across = np.cross(tangent, up_in_plane)
    if np.linalg.norm(across) < 1e-8:
        across = np.array([1.0, 0.0, 0.0])
    across /= np.linalg.norm(across)

    pts3d = np.asarray(section.vertices, dtype=float)
    rel = pts3d - origin
    width = float(np.ptp(rel @ across))
    height = float(np.ptp(rel @ up_in_plane))

    total = centerline.total_length_mm or 1.0
    return CurvilinearSection(
        s=float(s), s_fraction=float(np.clip(s / total, 0.0, 1.0)),
        center=origin, tangent=tangent,
        width_mm=width, height_mm=height,
        area_mm2=float(polygon.area),
        perimeter_mm=float(np.sum(np.linalg.norm(np.diff(coords, axis=0), axis=1))),
    )


def sections_along(mesh: trimesh.Trimesh, fractions: tuple[float, ...],
                   centerline: Centerline | None = None) -> list[CurvilinearSection]:
    """Curvilinear sections at the given fractions of *arc length* (not of the
    Y extent -- on a posed foot those are different curves)."""
    cl = centerline or build_centerline(mesh)
    if cl is None:
        return []
    out = []
    for f in fractions:
        sec = section_at(mesh, cl, f * cl.total_length_mm)
        if sec is not None:
            out.append(sec)
    return out
