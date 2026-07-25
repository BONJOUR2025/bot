"""Tests for curvilinear_sections — §5.4 / §26.13.

The property that matters: a rigid rotation cannot change any true
cross-section, so section metrics must be invariant under one. Measured on the
real Nikita foot, these sections drift 0.0% under a 20 deg rotation while the
Y=constant sections in mesh3d_service drift 7.5%."""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from app.services.curvilinear_sections import build_centerline, sections_along


def _rod(length=280.0, radius=25.0, sections=32, subdivisions=3):
    mesh = trimesh.creation.cylinder(radius=radius, height=length, sections=sections)
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    for _ in range(subdivisions):
        mesh = mesh.subdivide()
    mesh.apply_translation([0.0, length / 2.0, radius])
    return mesh


def test_centerline_follows_the_object_length():
    mesh = _rod()
    cl = build_centerline(mesh)
    assert cl is not None
    assert cl.total_length_mm == pytest.approx(280.0, rel=0.15)
    # tangents point along the rod (+Y), not across it
    assert abs(cl.tangents[len(cl.tangents) // 2][1]) > 0.9


def test_sections_are_invariant_under_rigid_rotation():
    """The core §5.4 property, and the bug that motivated building the
    centreline on a principal axis instead of on Y bins."""
    mesh = _rod()
    fractions = (0.35, 0.5, 0.7)
    before = [s.area_mm2 for s in sections_along(mesh, fractions)]

    rotated = mesh.copy()
    rotated.apply_transform(trimesh.transformations.rotation_matrix(np.radians(25), [1, 0, 0]))
    after = [s.area_mm2 for s in sections_along(rotated, fractions)]

    assert len(before) == len(after) == 3
    for b, a in zip(before, after):
        assert a == pytest.approx(b, rel=0.02)


def test_sections_are_invariant_under_translation():
    mesh = _rod()
    fractions = (0.4, 0.6)
    before = [s.area_mm2 for s in sections_along(mesh, fractions)]
    moved = mesh.copy()
    moved.apply_translation([13.0, -7.0, 21.0])
    after = [s.area_mm2 for s in sections_along(moved, fractions)]
    for b, a in zip(before, after):
        assert a == pytest.approx(b, rel=0.01)


def test_cylinder_sections_match_its_known_area():
    radius = 25.0
    mesh = _rod(radius=radius)
    sec = sections_along(mesh, (0.5,))[0]
    assert sec.area_mm2 == pytest.approx(np.pi * radius ** 2, rel=0.08)
    assert sec.width_mm == pytest.approx(2 * radius, rel=0.08)


def test_section_plane_is_orthogonal_to_the_tangent():
    mesh = _rod()
    cl = build_centerline(mesh)
    sec = sections_along(mesh, (0.5,), cl)[0]
    assert np.isclose(np.linalg.norm(sec.tangent), 1.0, atol=1e-6)


def test_degenerate_mesh_returns_no_centerline():
    tiny = trimesh.Trimesh(vertices=np.zeros((4, 3)), faces=np.array([[0, 1, 2]]))
    assert build_centerline(tiny) is None
    assert sections_along(tiny, (0.5,)) == []
