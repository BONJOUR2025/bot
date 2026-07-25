"""MVP piecewise local-frame foot deformation — stage 3 of
heel_toe_measurement_foot_deformation_visualization_spec.md ("§14.5:
MVP = piecewise local-frame deformation; Production = ARAP/cage" — this
implements the MVP half, deliberately not the production half).

Why not a rigid rotation of the whole foot, and not last_pose_service.py's
existing whole-foot vertical smoothstep lift: neither models what actually
happens when a flat-scanned foot is posed onto a last with a raised heel —
the rear segment needs to *rotate* around the ball line (the functional
hinge), and the front segment needs to follow the last's own sole curve, not
just shift up by a constant (§10-§12 of the spec).

Method (§13 of the spec, "рекомендуемая модель"): build ~120 cross-section
local frames (center + tangent + normal + binormal) along the foot's own
plantar centerline, build a *target* centerline (heel segment rotated around
the ball line by the last's measured heel angle; front segment's Z blended
toward the last's own bottom profile via a two-segment length mapping so a
last's decorative toe overhang doesn't stretch the toe unrealistically —
§16), derive target frames from that new centerline the same way, then
reproject every foot vertex from its local (a, b, c) coordinates in the
*original* frame into the corresponding *target* frame.

One deliberate deviation from the spec's own §13.4/§15 pseudocode: that
pseudocode reconstructs a vertex as `center + a*B + b*N` — two components,
implicitly assuming every vertex sits exactly on its cross-section's plane.
Real mesh vertices near a section boundary have a nonzero offset *along* the
section's own tangent too; dropping it would snap every vertex onto one of
~120 discrete rings, which is exactly the "ступенчатый артефакт" the spec's
§14.1 warns a naive piecewise method produces. This keeps a third component
(`c` along the tangent) so a vertex's fine along-length position is
preserved, not discretized — a direct fix for that named failure mode, not
scope creep.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh

from app.services.deformation_validation import validate_deformation
from app.services.last_bottom_profile import profile_z_at_y
from app.services.last_pose_measurements import measure_last_pose
from app.services.last_pose_service import _smoothstep, apply_pose
from app.services.scm_parser_service import _ball_line_mm

DEFAULT_N_SECTIONS = 120
_MIN_BAND_POINTS = 5

# Thresholds for trusting an automatic deformation (§17.4 of the spec: a
# disagreeing/low-quality result should fall back to "no pose applied"
# rather than be shown with false confidence). Calibrated against the real
# Prada-43-last/Nikita-foot pair (p95_edge_strain=0.145, flipped_face_
# fraction=0.0008 there) with generous headroom, since this is the only
# real pair available to calibrate against.
_MAX_P95_EDGE_STRAIN = 0.5
_MAX_FLIPPED_FACE_FRACTION = 0.05
_MIN_LAST_CONFIDENCE = 0.3


@dataclass
class SectionFrame:
    y: float
    center: np.ndarray     # (3,) world position of this section's plantar point
    tangent: np.ndarray    # (3,) unit, "T" -- along the centerline
    normal: np.ndarray     # (3,) unit, "N" -- roughly vertical
    binormal: np.ndarray   # (3,) unit, "B" -- roughly medial-lateral


def _frames_from_centerline(y_positions: np.ndarray, centers: np.ndarray) -> list[SectionFrame]:
    tangents = np.gradient(centers, axis=0)
    norms = np.linalg.norm(tangents, axis=1, keepdims=True)
    norms[norms < 1e-9] = 1.0
    tangents = tangents / norms

    world_up = np.array([0.0, 0.0, 1.0])
    normals = np.zeros_like(tangents)
    binormals = np.zeros_like(tangents)
    for i in range(len(tangents)):
        t = tangents[i]
        n = world_up - t * np.dot(world_up, t)  # Gram-Schmidt against the tangent
        n_norm = np.linalg.norm(n)
        n = n / n_norm if n_norm > 1e-8 else np.array([0.0, 0.0, 1.0])
        b = np.cross(t, n)
        b_norm = np.linalg.norm(b)
        b = b / b_norm if b_norm > 1e-8 else np.array([1.0, 0.0, 0.0])
        normals[i] = n
        binormals[i] = b

    return [
        SectionFrame(y=float(y_positions[i]), center=centers[i], tangent=tangents[i],
                     normal=normals[i], binormal=binormals[i])
        for i in range(len(y_positions))
    ]


def build_section_frames(mesh: trimesh.Trimesh, n_sections: int = DEFAULT_N_SECTIONS) -> list[SectionFrame]:
    """Plantar centerline frames along `mesh`'s own length (Y) axis — used
    both for the source (flat) foot and, on its raw centers, for the target
    curve derived from it."""
    y = mesh.vertices[:, 1]
    z = mesh.vertices[:, 2]
    y_min, y_max = float(y.min()), float(y.max())
    y_positions = np.linspace(y_min, y_max, n_sections)
    step = (y_max - y_min) / max(n_sections - 1, 1)
    band_half_width = max(step * 1.5, 1.0)

    centers_z = np.full(n_sections, np.nan)
    for i, yp in enumerate(y_positions):
        band = np.abs(y - yp) < band_half_width
        if band.sum() >= _MIN_BAND_POINTS:
            centers_z[i] = np.percentile(z[band], 2.0)

    nan_mask = np.isnan(centers_z)
    if nan_mask.any():
        valid = ~nan_mask
        if valid.sum() < 2:
            raise ValueError("insufficient_geometry_for_section_frames")
        centers_z[nan_mask] = np.interp(y_positions[nan_mask], y_positions[valid], centers_z[valid])

    centers = np.column_stack([np.zeros(n_sections), y_positions, centers_z])
    return _frames_from_centerline(y_positions, centers)


def _rotate_yz(vec: np.ndarray, cos_a: float, sin_a: float) -> np.ndarray:
    y_c, z_c = vec[1], vec[2]
    return np.array([vec[0], y_c * cos_a - z_c * sin_a, y_c * sin_a + z_c * cos_a])


def build_target_curve(
    foot_frames: list[SectionFrame], heel_height_mm: float, ball_line_foot_y: float,
    last_profile: list[dict], last_ball_line_y: float, last_toe_y: float,
) -> list[SectionFrame]:
    """Target frames: heel segment rotated around the ball line (§12.3-12.4),
    front segment blended toward the last's own bottom profile via the
    two-segment Y mapping (§16.2) so a last's decorative toe overhang doesn't
    stretch the foot's own toes to match it.

    The back segment rotates the *whole local frame* (center, tangent,
    normal, binormal) as one rigid rotation matrix per point, rather than
    rotating only the centerline and recomputing frames from its finite
    differences. The two are not equivalent: a point far from the
    centerline (e.g. an ankle-height vertex near y=0, whose local `b`/normal
    offset can be 5-10x the section spacing) is reconstructed as
    `center + a*B + b*N`, so any error in the *direction* of the target
    frame gets amplified by that offset. Recomputing the tangent from
    neighboring *rotated* centers conflates the true local curve direction
    with the lever-arm swing of points far from the pivot (their finite
    difference includes a `dtheta/dy * (center - pivot)` term that has
    nothing to do with local curve shape) -- confirmed empirically: it sent
    an ankle-height vertex to z=88mm under a ~7 degree rotation. Rotating
    the frame directly is an exact rigid transform for that segment, so it
    has no such artifact."""
    y_positions = np.array([f.y for f in foot_frames])
    heel_y = float(y_positions.min())
    foot_toe_y = float(y_positions.max())

    ball_idx = int(np.argmin(np.abs(y_positions - ball_line_foot_y)))
    pivot = foot_frames[ball_idx].center.copy()
    horizontal_dist = max(abs(pivot[1] - heel_y), 1e-6)
    alpha = float(np.arctan2(heel_height_mm, horizontal_dist))

    back_mask = y_positions <= ball_line_foot_y
    front_mask = ~back_mask

    target_frames: list[SectionFrame | None] = [None] * len(foot_frames)

    for i in np.where(back_mask)[0]:
        f = foot_frames[i]
        t = np.clip((ball_line_foot_y - f.y) / max(ball_line_foot_y - heel_y, 1e-6), 0.0, 1.0)
        # Negative: a single rotation about the pivot moves points on
        # opposite sides in opposite Z directions (seesaw). The heel sits
        # behind the pivot (rel_y < 0), and it must lift (rel_z increase),
        # which needs the opposite sign from the naive +alpha -- verified
        # empirically against the real Prada last/Nikita foot pair, where
        # +alpha instead sank the heel sole point by ~22mm into negative Z.
        angle = -alpha * float(_smoothstep(np.array(t)))
        cos_a, sin_a = np.cos(angle), np.sin(angle)
        new_center = pivot + _rotate_yz(f.center - pivot, cos_a, sin_a)
        target_frames[i] = SectionFrame(
            y=f.y, center=new_center,
            tangent=_rotate_yz(f.tangent, cos_a, sin_a),
            normal=_rotate_yz(f.normal, cos_a, sin_a),
            binormal=_rotate_yz(f.binormal, cos_a, sin_a),
        )

    front_idx = np.where(front_mask)[0]
    if front_idx.size:
        front_span = max(foot_toe_y - ball_line_foot_y, 1e-6)
        front_centers = []
        for i in front_idx:
            f = foot_frames[i]
            q = (f.y - ball_line_foot_y) / front_span
            mapped_y = last_ball_line_y + q * (last_toe_y - last_ball_line_y)
            z_last = profile_z_at_y(last_profile, mapped_y)
            w_toe = float(_smoothstep(np.array(q)))
            flat_z = f.center[2]
            new_z = flat_z if z_last is None else flat_z + w_toe * (z_last - flat_z)
            front_centers.append(np.array([f.center[0], f.y, new_z]))

        # Prepend the (already-rotated) pivot frame's own target center so the
        # front segment's finite-difference tangent is continuous with the
        # back segment at the seam, rather than starting cold.
        seam_center = target_frames[ball_idx].center
        chain_y = np.concatenate([[y_positions[ball_idx]], y_positions[front_idx]])
        chain_centers = np.vstack([seam_center, np.array(front_centers)])
        chain_frames = _frames_from_centerline(chain_y, chain_centers)
        for j, i in enumerate(front_idx):
            target_frames[i] = chain_frames[j + 1]

    return target_frames  # type: ignore[return-value]


def deform_foot_to_last_pose(
    foot_mesh: trimesh.Trimesh, foot_side: str | None,
    last_mesh: trimesh.Trimesh, last_side: str | None,
    n_sections: int = DEFAULT_N_SECTIONS,
) -> tuple[trimesh.Trimesh, dict]:
    """Both meshes are assumed already anatomically aligned (heel-anchored,
    mirrored to a common side) by the caller — this only reads their
    geometry, it doesn't register anything."""
    last_pose = measure_last_pose(last_mesh)

    foot_vertices = foot_mesh.vertices
    ball_line_foot_offset = _ball_line_mm(foot_vertices[:, 0], foot_vertices[:, 1])
    if ball_line_foot_offset is None:
        raise ValueError("no_ball_line_detected_on_foot")
    ball_line_foot_y = float(foot_vertices[:, 1].min()) + ball_line_foot_offset

    # The rotation is driven by the *effective* heel elevation (the height
    # difference between the last's heel-seat and ball-tread support patches),
    # never by the Z of its rearmost vertex -- see last_working_orientation.py
    # for why the latter is not a heel height at all. On a flat last this is
    # ~0 and the heel segment correctly stays put.
    heel_elevation = last_pose["effective_heel_elevation_mm"]

    foot_frames = build_section_frames(foot_mesh, n_sections=n_sections)
    target_frames = build_target_curve(
        foot_frames,
        heel_height_mm=heel_elevation,
        ball_line_foot_y=ball_line_foot_y,
        last_profile=last_pose["bottom_profile"],
        last_ball_line_y=last_pose["ball_line_y_mm"] if last_pose["ball_line_y_mm"] is not None
            else last_pose["heel_toe_detail"]["length_mm"] * 0.65,
        last_toe_y=last_pose["heel_toe_detail"]["y_max_mm"],
    )

    y_section = np.array([f.y for f in foot_frames])
    diffs = np.abs(foot_vertices[:, 1:2] - y_section[None, :])
    section_idx = np.argmin(diffs, axis=1)

    deformed_vertices = np.empty_like(foot_vertices)
    for i, frame in enumerate(foot_frames):
        mask = section_idx == i
        if not mask.any():
            continue
        rel = foot_vertices[mask] - frame.center
        a = rel @ frame.binormal
        b = rel @ frame.normal
        c = rel @ frame.tangent
        tgt = target_frames[i]
        deformed_vertices[mask] = (
            tgt.center
            + np.outer(a, tgt.binormal)
            + np.outer(b, tgt.normal)
            + np.outer(c, tgt.tangent)
        )

    deformed = foot_mesh.copy()
    deformed.vertices = deformed_vertices

    pose_info = {
        "source_geometry": "foot_flat",
        "target_geometry": "foot_last_pose",
        # What the pose actually used, and (separately) the descriptive
        # back-of-heel profile height it must not be confused with.
        "heel_height_mm": round(heel_elevation, 1),
        "effective_heel_elevation_mm": round(heel_elevation, 1),
        "rear_profile_height_mm": last_pose["heel_height_mm"],
        "orientation_confidence": last_pose["working_orientation"]["orientation_confidence"],
        "toe_spring_tip_mm": last_pose["toe_spring_tip_mm"],
        "ball_line_foot_mm": round(ball_line_foot_y, 2),
        "n_sections": n_sections,
        "last_pose": last_pose,
    }
    return deformed, pose_info


def _deformation_is_trustworthy(quality: dict, last_confidence: float) -> bool:
    if last_confidence < _MIN_LAST_CONFIDENCE:
        return False
    if quality["p95_edge_strain"] > _MAX_P95_EDGE_STRAIN:
        return False
    if quality["flipped_face_fraction"] > _MAX_FLIPPED_FACE_FRACTION:
        return False
    return True


def resolve_foot_pose(
    foot_mesh: trimesh.Trimesh, foot_side: str | None,
    last_mesh: trimesh.Trimesh, last_side: str | None,
    heel_height_mm: float | None = None, toe_spring_mm: float | None = None,
) -> tuple[trimesh.Trimesh, float | None, dict]:
    """Orchestrator: manual override (both fields given) keeps today's
    exact `apply_pose` behavior unchanged; otherwise attempts the automatic
    local-frame deformation and falls back to "no pose" (matching today's
    existing behavior when the manual fields are absent) if the last's
    measurement confidence is low or the resulting mesh fails validation.

    Returns `(mesh, pose_confidence, pose_details)` -- `pose_confidence`
    keeps the exact null-vs-float contract callers already rely on
    (`last_fit_hybrid_service.py`/`mesh_visualization_service.py` both
    store it as-is in their response), with `pose_details` as the new,
    additive field."""
    if heel_height_mm is not None and toe_spring_mm is not None:
        posed, confidence = apply_pose(foot_mesh, heel_height_mm, toe_spring_mm)
        return posed, confidence, {
            "method": "manual_v1",
            "heel_height_mm": heel_height_mm,
            "toe_spring_mm": toe_spring_mm,
        }

    try:
        deformed, pose_info = deform_foot_to_last_pose(foot_mesh, foot_side, last_mesh, last_side)
    except Exception as exc:
        # Any geometry this MVP doesn't handle (no ball line, degenerate
        # section bands, ...) falls back to "no pose" rather than raising --
        # the same graceful-absence behavior today's apply_pose already has
        # when its manual fields are unset.
        return foot_mesh, None, {"method": "none", "reason": "deformation_failed", "error": str(exc)}

    quality = validate_deformation(foot_mesh, deformed)
    last_confidence = pose_info["last_pose"]["confidence"]
    if not _deformation_is_trustworthy(quality, last_confidence):
        return foot_mesh, None, {
            "method": "none",
            "attempted_method": "local_frames_v1",
            "quality": quality,
            "last_pose": pose_info["last_pose"],
            "reason": "validation_failed_or_low_confidence",
        }

    pose_info["method"] = "local_frames_v1"
    pose_info["quality"] = quality
    return deformed, round(last_confidence, 3), pose_info
