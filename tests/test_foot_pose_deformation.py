"""Tests for foot_pose_deformation — synthetic geometry per the spec's own
§26.3 (rotation around the ball line) and §26.4 (cylindrical local-frame
mapping) test descriptions. Full end-to-end (measure_last_pose -> ball line
detection -> deform_foot_to_last_pose) validation against the real Prada 43
last / Nikita foot pair was done ad hoc during development, not committed
here -- see foot_pose_deformation.py's own module/function docstrings for
the sign-convention bug that real-data check caught (a naive +alpha rotation
sank the heel instead of lifting it, since a rotation about a single pivot
moves points on opposite sides in opposite Z directions)."""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from app.services.foot_pose_deformation import (
    build_section_frames,
    build_target_curve,
    deform_foot_to_last_pose,
)


def _cylinder_foot(length=280.0, radius=20.0, sections=48):
    """A rod lying along Y, resting on the ground (its lowest generatrix at
    Z=0) -- the spec's own "cylindrical test object" (§26.4): uniform
    cross-section, so any change in per-section width/area after
    deformation is unambiguously a bug, not foot-shape noise."""
    mesh = trimesh.creation.cylinder(radius=radius, height=length, sections=sections)
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    mesh.apply_translation([0.0, length / 2.0, radius])
    return mesh


def test_build_section_frames_tracks_flat_sole():
    mesh = _cylinder_foot()
    frames = build_section_frames(mesh, n_sections=60)
    assert len(frames) == 60
    for f in frames:
        assert f.center[2] == pytest.approx(0.0, abs=1.0)
    ys = [f.y for f in frames]
    assert ys[0] == pytest.approx(0.0, abs=0.5)
    assert ys[-1] == pytest.approx(280.0, abs=0.5)


def test_build_target_curve_pivot_is_stationary_and_preserves_distances():
    mesh = _cylinder_foot()
    frames = build_section_frames(mesh, n_sections=60)
    heel_height_mm = 20.0
    ball_line_foot_y = 140.0  # midpoint
    flat_profile = [{"y": 0.0, "z": 0.0}, {"y": 280.0, "z": 0.0}]  # isolate the rotation, no toe spring

    target = build_target_curve(
        frames, heel_height_mm=heel_height_mm, ball_line_foot_y=ball_line_foot_y,
        last_profile=flat_profile, last_ball_line_y=ball_line_foot_y, last_toe_y=280.0,
    )

    ys = np.array([f.y for f in frames])
    ball_idx = int(np.argmin(np.abs(ys - ball_line_foot_y)))
    # §26.3: pivot doesn't move
    assert np.allclose(target[ball_idx].center, frames[ball_idx].center, atol=1e-6)

    pivot = frames[ball_idx].center
    # §26.3: "длины локальных сечений сохраняются" -- a rigid rotation about
    # the pivot preserves each point's distance to it.
    for i in range(ball_idx + 1):
        orig_dist = np.linalg.norm(frames[i].center - pivot)
        new_dist = np.linalg.norm(target[i].center - pivot)
        assert new_dist == pytest.approx(orig_dist, abs=0.05)

    # §26.3: the heel reaches (approximately) the target height. Exact value
    # is horizontal_dist*sin(atan2(heel_height_mm, horizontal_dist)), which
    # only equals heel_height_mm in the small-angle limit -- here
    # horizontal_dist (~140mm) >> heel_height_mm (20mm), so they agree to
    # well under 1mm.
    heel_rise = target[0].center[2] - frames[0].center[2]
    assert heel_rise == pytest.approx(heel_height_mm, abs=0.5)
    # and it's a rise, not the sign-bug regression that sank it instead.
    assert heel_rise > 0


def test_deform_foot_to_last_pose_preserves_cross_section_width():
    """§26.4: per-section width before/after must match -- the piecewise
    reprojection re-expresses each vertex's *same* local (a, b, c)
    coordinates in a new frame, a per-section isometry by construction, so
    this should hold almost exactly. A gentle taper (not a uniform radius)
    is used so _ball_line_mm's width-variation-based landmark detection has
    something to lock onto -- a perfectly uniform cylinder has no width
    signal at all."""
    radius = 20.0
    length = 280.0
    mesh = trimesh.creation.cylinder(radius=radius, height=length, sections=48)
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    mesh.apply_translation([0.0, length / 2.0, radius])
    # trimesh's cylinder() only has two rings (top/bottom) along its length --
    # _ball_line_mm's landmark search bins the length into 100 slices needing
    # >=5 points each, so subdivide to get real longitudinal density before
    # tapering (taper is computed from the *subdivided* vertex Y positions).
    for _ in range(5):
        mesh = mesh.subdivide()
    y_frac = np.clip(mesh.vertices[:, 1] / length, 0.0, 1.0)
    taper = 1.15 - 0.30 * y_frac  # wider at the heel, narrower at the toe
    mesh.vertices[:, 0] *= taper

    last_mesh = trimesh.creation.box(extents=[2 * radius * 1.3, length + 10.0, 70.0])
    last_mesh.apply_translation([0.0, (length + 10.0) / 2.0, 35.0])

    deformed, pose_info = deform_foot_to_last_pose(mesh, "left", last_mesh, "left")
    assert pose_info["n_sections"] > 0

    # subdivide() only adds vertices at discrete ring positions (~8.75mm
    # apart here, not a continuum) -- band tolerance has to comfortably
    # cover half that spacing to be sure of hitting a ring.
    for frac in (0.1, 0.3, 0.7, 0.9):
        y0 = frac * length
        idx = np.where(np.abs(mesh.vertices[:, 1] - y0) < 4.5)[0]
        assert len(idx) > 5
        orig_width = mesh.vertices[idx, 0].max() - mesh.vertices[idx, 0].min()
        def_width = deformed.vertices[idx, 0].max() - deformed.vertices[idx, 0].min()
        assert def_width == pytest.approx(orig_width, rel=0.1, abs=1.0)
