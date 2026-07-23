"""Anatomically-constrained registration between a foot mesh and a last
(cavity) mesh — stage 4 of the slice_v1 -> hybrid_v2 migration (see
docs/last_fit_system_overview.md and the migration plan).

Why not a plain free-form ICP over the whole surface (the migration plan is
explicit about this, §9): a last is *deliberately* different from the foot
it's meant to fit — longer in the toe, a built-up heel, different curvature.
An unconstrained ICP will happily rotate/translate the foot to minimize
average surface error by, say, sliding it toward the (longer) toe or twisting
it to average out a real medial/lateral conflict away — exactly the wrong
thing for a fit-diagnosis tool, which needs the *disagreement* preserved, not
optimized away.

What this does instead:

1. Initial alignment is mostly already true by construction: both slice_v1's
   parsers (scm_parser_service.py, stl_parser_service.py) anchor every scan
   to the same coordinate convention (Y=0 at heel, Z=0 at the sole) before
   any of this runs, and mirrors a last onto the requested foot side the same
   way last_fit_service._mirror_profile already does for the 2D profile.
   Mirroring is a reflection (fixes left/right sidedness), not the "scale"
   the migration plan forbids — those are different operations.
2. A residual few-mm/few-degree misalignment is what's actually left, and
   that's what a *masked, scale-locked* ICP refines — restricted to regions
   the migration plan calls anatomically reliable for alignment (heel,
   plantar/sole, ball) and, per stage 2's own finding on this scanner's data
   (see mesh3d_service.py's module docstring), additionally capped by height
   to avoid the shin/ankle region, which tapers with no distinctive shape to
   lock onto and would just add alignment noise.
3. Confidence (`registration_confidence`) is an explicit, documented
   heuristic, not a calibrated probability — real calibration against actual
   fittings is stage 9 of the migration plan and out of scope here.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh

# Registration mask: zones the migration plan calls anatomically reliable for
# alignment, as fractions of foot length from the heel (Y=0).
_HEEL_FRAC_MAX = 0.25
_BALL_FRAC = (0.55, 0.80)
# Above this height, cross-sections keep narrowing all the way up with no
# distinctive foot-specific shape to lock onto (confirmed on a real reference
# scan — see mesh3d_service.py) — excluded from the alignment mask so ICP
# isn't pulled around by an ambiguous, nearly rotationally-symmetric region.
_MASK_MAX_Z_MM = 50.0
_MIN_MASK_POINTS = 20

# A point farther than this from the target surface, after alignment, isn't
# counted as a supporting ("inlier") match for confidence purposes — a few mm
# is in line with the scan/landmark noise already assumed elsewhere in this
# codebase (see last_fit_service.py's GIRTH_UNCERTAINTY_MM).
_INLIER_DISTANCE_MM = 3.0

# ICP re-queries closest points every iteration -- on a real reference scan
# pair the full heel+ball mask came to ~22k points and took ~20s to converge
# (max_iterations iterations x closest-point query over a 110k-face mesh).
# A deterministic, evenly-spaced subsample keeps the same spatial coverage
# with a bounded, reproducible cost.
_MAX_ICP_SOURCE_POINTS = 2000


def _subsample_evenly(points: np.ndarray, max_points: int) -> np.ndarray:
    if len(points) <= max_points:
        return points
    stride = len(points) // max_points
    return points[::stride][:max_points]


@dataclass
class RegistrationResult:
    transform: np.ndarray  # 4x4, maps the *original* (post initial-align) foot vertices
    aligned_foot_vertices: np.ndarray
    translation_mm: float
    rotation_deg: float
    inlier_ratio: float
    registration_confidence: float
    mask_point_count: int

    def as_dict(self) -> dict:
        return {
            "translation_mm": round(self.translation_mm, 2),
            "rotation_deg": round(self.rotation_deg, 2),
            "inlier_ratio": round(self.inlier_ratio, 3),
            "registration_confidence": round(self.registration_confidence, 3),
            "mask_point_count": self.mask_point_count,
        }


def _heel_band_x_offset(vertices: np.ndarray, heel_frac: float = 0.15) -> float:
    y = vertices[:, 1]
    length = y.max() - y.min()
    heel = y < y.min() + length * heel_frac
    if not heel.any():
        return 0.0
    return float(vertices[heel, 0].mean())


def initial_align(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Heel-anchor (Y=0) + sole-anchor (Z=0) + X-center on the heel band —
    the same convention _heel_centered (scm_parser_service.py) already
    applies for the 2D profile pipeline. Returns a new mesh; input untouched."""
    v = mesh.vertices
    dy = -float(v[:, 1].min())
    dz = -float(v[:, 2].min())
    shifted = mesh.copy()
    shifted.apply_translation([0.0, dy, dz])
    dx = -_heel_band_x_offset(shifted.vertices)
    shifted.apply_translation([dx, 0.0, 0.0])
    return shifted


def mirror_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Reflect a mesh across the X=0 (medial-lateral) plane — a last's left
    and right are mirror-identical (same assumption last_fit_service.py's
    _mirror_profile already makes), so this is how a single stored last shape
    gets checked against either foot side. `apply_transform` with a
    negative-determinant matrix keeps the mesh watertight and correctly
    re-winds faces (verified: volume/watertightness unchanged after mirroring
    a synthetic box) — this is a reflection, not the "scale" the migration
    plan prohibits elsewhere."""
    reflected = mesh.copy()
    matrix = np.eye(4)
    matrix[0, 0] = -1.0
    reflected.apply_transform(matrix)
    return reflected


def _alignment_mask(vertices: np.ndarray, foot_length_mm: float) -> np.ndarray:
    y, z = vertices[:, 1], vertices[:, 2]
    frac = y / foot_length_mm
    heel = frac <= _HEEL_FRAC_MAX
    ball = (frac >= _BALL_FRAC[0]) & (frac <= _BALL_FRAC[1])
    return (heel | ball) & (z <= _MASK_MAX_Z_MM)


def _rotation_angle_deg(matrix: np.ndarray) -> float:
    rot = matrix[:3, :3]
    trace = np.clip(np.trace(rot), -1.0, 3.0)
    cos_angle = np.clip((trace - 1.0) / 2.0, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_angle)))


def register_foot_to_cavity(
    foot_mesh: trimesh.Trimesh, foot_side: str | None,
    cavity_mesh: trimesh.Trimesh, cavity_side: str | None,
    max_iterations: int = 20,
) -> tuple[RegistrationResult, trimesh.Trimesh, trimesh.Trimesh]:
    """Align `foot_mesh` onto `cavity_mesh`'s frame. Returns (result,
    initial_aligned_foot_mesh, initial_aligned_cavity_mesh) — the caller
    applies `result.transform` to get the final aligned foot vertices
    (already in `result.aligned_foot_vertices`); the returned meshes are
    handed back too since stage 3's signed-distance step needs a full mesh,
    not just vertices, for the *cavity* side, and callers may want the
    aligned-but-not-ICP-refined cavity mesh for consistency."""
    if cavity_side and foot_side and cavity_side != foot_side:
        cavity_mesh = mirror_mesh(cavity_mesh)

    foot_a = initial_align(foot_mesh)
    cavity_a = initial_align(cavity_mesh)

    foot_length_mm = float(foot_a.vertices[:, 1].max())
    mask = _alignment_mask(foot_a.vertices, foot_length_mm)

    if mask.sum() < _MIN_MASK_POINTS:
        # Not enough reliable geometry to refine against (e.g. a degenerate
        # or very small scan) — report identity-transform alignment with
        # zero confidence rather than guessing.
        result = RegistrationResult(
            transform=np.eye(4),
            aligned_foot_vertices=foot_a.vertices,
            translation_mm=0.0, rotation_deg=0.0,
            inlier_ratio=0.0, registration_confidence=0.0,
            mask_point_count=int(mask.sum()),
        )
        return result, foot_a, cavity_a

    source_points = _subsample_evenly(foot_a.vertices[mask], _MAX_ICP_SOURCE_POINTS)
    matrix, _transformed, _cost = trimesh.registration.icp(
        source_points, cavity_a,
        initial=np.eye(4), max_iterations=max_iterations,
        scale=False, reflection=False,
    )

    aligned_vertices = trimesh.transform_points(foot_a.vertices, matrix)
    aligned_mask_points = trimesh.transform_points(source_points, matrix)
    _closest, distances, _tri = trimesh.proximity.closest_point(cavity_a, aligned_mask_points)
    inlier_ratio = float((distances <= _INLIER_DISTANCE_MM).mean())

    translation_mm = float(np.linalg.norm(matrix[:3, 3]))
    rotation_deg = _rotation_angle_deg(matrix)

    # Confidence: an explicit, documented heuristic (not a calibrated
    # probability — see module docstring). Rewards a high inlier ratio,
    # penalizes large residual translation/rotation (a "successful" ICP that
    # still needed a big correction says the initial anatomical alignment was
    # off, which is itself worth flagging as lower-confidence).
    confidence = inlier_ratio
    confidence -= 0.02 * max(0.0, rotation_deg - 5.0)
    confidence -= 0.01 * max(0.0, translation_mm - 5.0)
    confidence = float(np.clip(confidence, 0.0, 1.0))

    result = RegistrationResult(
        transform=matrix,
        aligned_foot_vertices=aligned_vertices,
        translation_mm=translation_mm,
        rotation_deg=rotation_deg,
        inlier_ratio=inlier_ratio,
        registration_confidence=confidence,
        mask_point_count=int(mask.sum()),
    )
    return result, foot_a, cavity_a
