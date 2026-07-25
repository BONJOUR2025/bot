"""Heel-fixed rigid registration -- §9 of research_foot_last_pose_fit_
technical_report_for_claude.md.

Registration's only job is to bring the foot and the last into one coordinate
frame (§9.1). It must not scale the foot, reshape it, pull the toes toward the
last's toe, or quietly absorb a ball-line mismatch -- those disagreements are
the *output* of the analysis, and an optimiser that minimises them away
destroys the very signal the tool exists to report.

What this replaces: `last_registration_service.register_foot_to_cavity` runs a
masked ICP over the heel and ball zones. ICP minimises total surface error, so
it happily slides the heel to buy a better ball fit. Measured on the real
Nikita/Prada pair, the heel moved 1.14mm in Y, 1.44mm in X and 1.69mm in Z --
against §9.5's 0.1mm budget. Worse, that motion is indistinguishable from a
real medial conflict downstream: §5 of the audit document notes a 3mm shift
alone can manufacture a "medial conflict / lateral gap" verdict out of nothing.

Here the heel is pinned by construction (§9.2): pternion Y, heel centre X and
plantar heel Z are matched exactly, and the only free parameter is a rotation
about Z that aligns the heel->ball direction. Scale is fixed at 1. MTH1/MTH5
are never used as anchors -- where they land afterwards is a result (§9.3).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh

from app.services.foot_landmarks import FootLandmarks, detect_foot_landmarks

# §9.5 acceptance budget for the pinned heel quantities.
_HEEL_TOLERANCE_MM = 0.1


@dataclass
class HeelFixedRegistration:
    transform: np.ndarray                 # 4x4 applied to the foot
    rotation_deg: float                   # about Z only
    translation_mm: float
    posterior_heel_delta_y: float
    heel_center_delta_x: float
    plantar_heel_delta_z: float
    scale: float
    confidence: float
    warnings: list[str] = field(default_factory=list)
    method: str = "heel_fixed_v1"

    @property
    def within_tolerance(self) -> bool:
        return (abs(self.posterior_heel_delta_y) < _HEEL_TOLERANCE_MM
                and abs(self.heel_center_delta_x) < _HEEL_TOLERANCE_MM
                and abs(self.plantar_heel_delta_z) < _HEEL_TOLERANCE_MM)

    def as_dict(self) -> dict:
        return {
            "rotation_deg": round(self.rotation_deg, 2),
            "translation_mm": round(self.translation_mm, 2),
            "posterior_heel_delta_y_mm": round(self.posterior_heel_delta_y, 3),
            "heel_center_delta_x_mm": round(self.heel_center_delta_x, 3),
            "plantar_heel_delta_z_mm": round(self.plantar_heel_delta_z, 3),
            "scale": self.scale,
            "within_tolerance": self.within_tolerance,
            "confidence": round(self.confidence, 3),
            "warnings": list(self.warnings),
            "method": self.method,
        }


def _rotation_about_z(theta: float) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    m = np.eye(4)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    return m


def _translation(vec: np.ndarray) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = vec
    return m


def _heel_axis_angle(landmarks: FootLandmarks) -> float | None:
    """Heading of the heel->ball direction in the XY plane."""
    ball = landmarks.ball_center
    if ball is None or landmarks.plantar_heel_center is None:
        return None
    d = ball - landmarks.plantar_heel_center.position
    if abs(d[0]) < 1e-9 and abs(d[1]) < 1e-9:
        return None
    return float(np.arctan2(d[0], d[1]))  # 0 = straight along +Y


def register_foot_to_last(
    foot_mesh: trimesh.Trimesh,
    last_mesh: trimesh.Trimesh,
    foot_side: str | None = None,
    last_side: str | None = None,
    foot_landmarks: FootLandmarks | None = None,
    last_landmarks: FootLandmarks | None = None,
) -> tuple[HeelFixedRegistration, trimesh.Trimesh, trimesh.Trimesh]:
    """Place `foot_mesh` in `last_mesh`'s frame with the heel pinned.

    Returns (result, registered_foot, last_mesh_used). The last is returned
    unchanged apart from mirroring when the two sides differ -- §19.1 requires
    each stage to hand back new objects and leave its inputs alone.
    """
    warnings: list[str] = []

    if last_side and foot_side and last_side != foot_side:
        matrix = np.eye(4)
        matrix[0, 0] = -1.0
        last_mesh = last_mesh.copy()
        last_mesh.apply_transform(matrix)

    fl = foot_landmarks or detect_foot_landmarks(foot_mesh, side=foot_side)
    ll = last_landmarks or detect_foot_landmarks(last_mesh, side=last_side or foot_side)
    if fl.plantar_heel_center is None or ll.plantar_heel_center is None:
        warnings.append("plantar_heel_center_missing")
        identity = HeelFixedRegistration(np.eye(4), 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, warnings)
        return identity, foot_mesh.copy(), last_mesh

    # 1. Rotation about Z aligning the two heel->ball headings (§9.2 item 4).
    theta_foot = _heel_axis_angle(fl)
    theta_last = _heel_axis_angle(ll)
    if theta_foot is None or theta_last is None:
        theta = 0.0
        warnings.append("heel_to_ball_axis_unavailable_rotation_skipped")
    else:
        theta = theta_last - theta_foot

    # Rotate about the foot's own plantar heel centre so that point cannot move.
    pivot = fl.plantar_heel_center.position
    rot = _translation(pivot) @ _rotation_about_z(theta) @ _translation(-pivot)

    # 2. Translation pinning the three heel quantities exactly (§9.2 items 1-3).
    #    Y from the posterior heel, X from the heel centre, Z from the plantar
    #    heel -- each taken from the landmark that defines it, not averaged.
    foot_v = trimesh.transform_points(np.asarray(foot_mesh.vertices, dtype=float), rot)
    foot_pternion = trimesh.transform_points(fl.pternion.position[None, :], rot)[0] \
        if fl.pternion is not None else None
    foot_heel = trimesh.transform_points(fl.plantar_heel_center.position[None, :], rot)[0]

    dy = (ll.pternion.position[1] - foot_pternion[1]) if (foot_pternion is not None and ll.pternion) \
        else (ll.plantar_heel_center.position[1] - foot_heel[1])
    dx = ll.plantar_heel_center.position[0] - foot_heel[0]
    dz = ll.plantar_heel_center.position[2] - foot_heel[2]
    shift = np.array([dx, dy, dz])

    transform = _translation(shift) @ rot
    registered = foot_mesh.copy()
    registered.vertices = trimesh.transform_points(np.asarray(foot_mesh.vertices, dtype=float), transform)

    # 3. §9.5 verification, measured rather than assumed.
    fl_after = trimesh.transform_points(
        np.vstack([
            fl.pternion.position if fl.pternion is not None else fl.plantar_heel_center.position,
            fl.plantar_heel_center.position,
        ]), transform)
    pternion_after, heel_after = fl_after[0], fl_after[1]
    target_pternion = ll.pternion.position if ll.pternion is not None else ll.plantar_heel_center.position
    delta_y = float(pternion_after[1] - target_pternion[1])
    delta_x = float(heel_after[0] - ll.plantar_heel_center.position[0])
    delta_z = float(heel_after[2] - ll.plantar_heel_center.position[2])

    scale = float(np.linalg.det(transform[:3, :3]))
    if not np.isclose(scale, 1.0, atol=1e-6):
        warnings.append("transform_is_not_rigid")

    confidence = min(fl.confidence, ll.confidence)
    if abs(np.degrees(theta)) > 15.0:
        warnings.append("large_heel_axis_correction")
        confidence *= 0.5

    result = HeelFixedRegistration(
        transform=transform,
        rotation_deg=float(np.degrees(theta)),
        translation_mm=float(np.linalg.norm(shift)),
        posterior_heel_delta_y=delta_y,
        heel_center_delta_x=delta_x,
        plantar_heel_delta_z=delta_z,
        scale=1.0,
        confidence=float(np.clip(confidence, 0.0, 1.0)),
        warnings=warnings,
    )
    if not result.within_tolerance:
        result.warnings.append("heel_not_pinned_within_tolerance")
    return result, registered, last_mesh
