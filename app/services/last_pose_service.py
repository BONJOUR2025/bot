"""Foot pose transform for a last's heel height and toe spring — stage 5 of
the slice_v1 -> hybrid_v2 migration (see docs/last_fit_system_overview.md and
the migration plan).

A foot is scanned standing flat on a platform. A last has a raised heel seat
and a curved-up toe (toe spring) built into its own shape. Comparing the flat
foot directly against that shaped last — which is what slice_v1 and stages
0-4 of hybrid_v2 all still do — produces systematic false height conflicts:
the last's heel/toe curve up for a reason (so the finished shoe's sole can
roll through a step) that has nothing to do with the foot being too tall
there.

Per the migration plan (§8): "плавная деформация, не жёсткий поворот всей
стопы" — a smooth per-vertex lift along Z, anchored at the already-computed
ball line (scm_parser_service._ball_line_mm), not a rigid rotation of the
whole foot. Only Z moves; X/Y (and therefore length/width) are untouched, and
there is no scaling anywhere in this module.

This only ever runs when a last has *both* heel_height_mm and toe_spring_mm
recorded (`app/data/last_repository.py`, set at upload time in
`app/api/lasts.py`) — no invented defaults for a last that didn't provide
them; the foot is compared flat, as before, and `pose_confidence` says so.
"""
from __future__ import annotations

import numpy as np
import trimesh

from app.services.scm_parser_service import _ball_line_mm


def _smoothstep(t: np.ndarray) -> np.ndarray:
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def apply_pose(
    foot_mesh: trimesh.Trimesh,
    heel_height_mm: float | None,
    toe_spring_mm: float | None,
) -> tuple[trimesh.Trimesh, float | None]:
    """Lift the foot mesh toward a last's heel height / toe spring.

    Returns (posed_mesh, pose_confidence). `posed_mesh` is the *unchanged*
    input when either parameter is missing or the foot's own ball line can't
    be found — pose_confidence is then `None`, meaning "not applied", not
    "applied with low confidence". Input mesh is assumed already
    heel-anchored (Y=0 at heel) by last_registration_service.initial_align.
    """
    if heel_height_mm is None or toe_spring_mm is None:
        return foot_mesh, None

    vertices = foot_mesh.vertices
    y = vertices[:, 1]
    length = float(y.max())
    if length <= 0:
        return foot_mesh, None

    ball_line = _ball_line_mm(vertices[:, 0], y)
    if ball_line is None or not (0.0 < ball_line < length):
        return foot_mesh, None

    z_lift = np.zeros(len(vertices))
    heel_zone = y <= ball_line
    toe_zone = ~heel_zone

    # Full heel_height_mm at the heel (y=0), smoothly down to 0 at the ball line.
    heel_t = 1.0 - (y[heel_zone] / ball_line)
    z_lift[heel_zone] = heel_height_mm * _smoothstep(heel_t)

    # 0 at the ball line, smoothly up to full toe_spring_mm at the toe tip.
    toe_t = (y[toe_zone] - ball_line) / (length - ball_line)
    z_lift[toe_zone] = toe_spring_mm * _smoothstep(toe_t)

    posed = foot_mesh.copy()
    posed.vertices = vertices + np.column_stack(
        [np.zeros(len(vertices)), np.zeros(len(vertices)), z_lift]
    )
    return posed, 1.0
