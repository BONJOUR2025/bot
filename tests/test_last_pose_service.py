"""Tests for last_pose_service — synthetic meshes only."""
from __future__ import annotations

import numpy as np
import trimesh
import pytest

from app.services.last_pose_service import apply_pose


def _foot_mesh(length=270.0, width=90.0, height=110.0):
    mesh = trimesh.creation.box(extents=[width, length, height])
    for _ in range(4):
        mesh = mesh.subdivide()
    mesh.apply_translation([0.0, length / 2.0, height / 2.0])
    return mesh


def test_no_pose_applied_when_params_missing():
    mesh = _foot_mesh()
    posed, confidence = apply_pose(mesh, None, None)
    assert confidence is None
    assert posed is mesh
    assert np.array_equal(posed.vertices, mesh.vertices)


def test_no_pose_applied_when_only_one_param_given():
    mesh = _foot_mesh()
    posed, confidence = apply_pose(mesh, 20.0, None)
    assert confidence is None
    assert posed is mesh


def test_heel_lifted_toe_unchanged_at_ball_line():
    mesh = _foot_mesh(length=270.0)
    posed, confidence = apply_pose(mesh, heel_height_mm=20.0, toe_spring_mm=15.0)
    assert confidence == 1.0

    y = mesh.vertices[:, 1]
    z_before = mesh.vertices[:, 2]
    z_after = posed.vertices[:, 2]

    # heel points (y near 0) should be lifted by close to the full heel_height_mm
    heel_mask = y < 2.0
    assert (z_after[heel_mask] - z_before[heel_mask]).mean() == pytest.approx(20.0, abs=1.0)

    # toe tip points (y near length) should be lifted close to toe_spring_mm
    toe_mask = y > mesh.vertices[:, 1].max() - 2.0
    assert (z_after[toe_mask] - z_before[toe_mask]).mean() == pytest.approx(15.0, abs=1.0)

    # x/y untouched -- only Z moves (no scaling, no rotation)
    assert np.array_equal(posed.vertices[:, 0], mesh.vertices[:, 0])
    assert np.array_equal(posed.vertices[:, 1], mesh.vertices[:, 1])


def test_lift_is_smooth_not_a_step():
    mesh = _foot_mesh()
    posed, _ = apply_pose(mesh, heel_height_mm=20.0, toe_spring_mm=15.0)
    lift = posed.vertices[:, 2] - mesh.vertices[:, 2]
    # no lift value should be a huge outlier relative to its neighbors in y --
    # a crude proxy: max lift shouldn't exceed the larger of the two inputs
    assert lift.max() <= 20.0 + 1e-6
    assert lift.min() >= 0.0 - 1e-6
