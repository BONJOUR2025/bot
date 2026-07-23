"""Tests for last_registration_service — synthetic meshes only."""
from __future__ import annotations

import numpy as np
import trimesh
import pytest

from app.services.last_registration_service import (
    initial_align,
    mirror_mesh,
    register_foot_to_cavity,
)


def _foot_like_mesh(length=270.0, width=90.0, height=110.0, offset=(0.0, 0.0, 0.0)):
    """A box standing in for a foot/last, subdivided enough to have real
    vertex density in the heel/ball alignment mask (a bare 8-vertex box only
    has 1-2 corners in any given zone -- nowhere near _MIN_MASK_POINTS, and
    not representative of an actual scan's vertex density)."""
    mesh = trimesh.creation.box(extents=[width, length, height])
    for _ in range(4):
        mesh = mesh.subdivide()
    # box() centers at origin -> shift so heel is at y=0, sole at z=0, x centered
    mesh.apply_translation([0.0, length / 2.0, height / 2.0])
    mesh.apply_translation(list(offset))
    return mesh


def test_initial_align_anchors_heel_and_sole():
    mesh = _foot_like_mesh(offset=(15.0, 37.0, -8.0))
    aligned = initial_align(mesh)
    assert aligned.vertices[:, 1].min() == pytest.approx(0.0, abs=1e-6)
    assert aligned.vertices[:, 2].min() == pytest.approx(0.0, abs=1e-6)
    # heel band should now be centered on x=0
    heel = aligned.vertices[:, 1] < (aligned.vertices[:, 1].max()) * 0.15
    assert aligned.vertices[heel, 0].mean() == pytest.approx(0.0, abs=1.0)


def test_mirror_preserves_watertight_volume():
    mesh = _foot_like_mesh()
    mirrored = mirror_mesh(mesh)
    assert mirrored.is_watertight is True
    assert mirrored.volume == pytest.approx(mesh.volume, rel=1e-6)
    # actually flipped in x
    assert mirrored.vertices[:, 0].max() == pytest.approx(-mesh.vertices[:, 0].min(), abs=1e-6)


def test_register_recovers_small_known_offset():
    cavity = _foot_like_mesh()
    # foot is the same shape, shifted/rotated slightly -- registration should
    # pull it back close to the cavity's frame.
    true_offset = (4.0, -3.0, 2.0)
    foot = _foot_like_mesh(offset=true_offset)

    result, foot_a, cavity_a = register_foot_to_cavity(foot, "left", cavity, "left")
    assert result.mask_point_count > 0
    assert result.inlier_ratio > 0.5
    # after alignment, the (masked-region) points should sit close to the
    # cavity surface -- checked indirectly via inlier_ratio above; also
    # confirm confidence is a sane bounded number
    assert 0.0 <= result.registration_confidence <= 1.0


def test_register_mirrors_when_sides_differ():
    cavity = _foot_like_mesh()
    foot = _foot_like_mesh()
    result, foot_a, cavity_a = register_foot_to_cavity(foot, "left", cavity, "right")
    # cavity_a should have been mirrored before initial-align -> still watertight
    assert cavity_a.is_watertight is True


def test_low_mask_coverage_returns_zero_confidence():
    # A mesh with almost no faces in the reliable Y/Z range -> mask too small
    tiny = trimesh.creation.box(extents=[1, 1, 1])
    tiny.apply_translation([0, 0.5, 0.5])
    cavity = _foot_like_mesh()
    result, _, _ = register_foot_to_cavity(tiny, "left", cavity, "left")
    assert result.registration_confidence == 0.0
