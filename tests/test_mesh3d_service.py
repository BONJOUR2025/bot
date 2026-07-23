"""Tests for mesh3d_service — synthetic meshes only (trimesh primitives)."""
from __future__ import annotations

import numpy as np
import trimesh
import pytest

from app.services.mesh3d_service import (
    MAX_AUTO_REPAIR_BOUNDARY_MM,
    bidirectional_surface_distance,
    distance_aggregates,
    mesh_quality_report,
    repair_small_holes,
    surface_distance,
)


def _box(extents=(100, 200, 80)):
    return trimesh.creation.box(extents=list(extents))


def _box_with_small_hole(n_faces_removed: int = 1):
    # A box's default 12 faces are huge (whole sides) — removing even one
    # leaves a hole with a boundary of hundreds of mm. Subdivide first so
    # "remove one face" actually means a small, technical-gap-sized hole,
    # like a real scanner might leave, not a missing whole side.
    mesh = _box()
    for _ in range(6):
        mesh = mesh.subdivide()
    keep = np.ones(len(mesh.faces), dtype=bool)
    keep[:n_faces_removed] = False
    mesh.update_faces(keep)
    mesh.remove_unreferenced_vertices()
    return mesh


def _two_disconnected_boxes():
    a = trimesh.creation.box(extents=[10, 10, 10])
    b = trimesh.creation.box(extents=[10, 10, 10])
    b.apply_translation([200, 0, 0])
    return trimesh.util.concatenate([a, b])


def test_clean_watertight_box_is_fully_valid():
    report = mesh_quality_report(_box())
    assert report.watertight is True
    assert report.winding_consistent is True
    assert report.is_volume is True
    assert report.degenerate_faces == 0
    assert report.duplicate_faces == 0
    assert report.connected_components == 1
    assert report.open_boundary_mm == 0.0
    assert report.valid_for_signed_distance is True
    assert report.valid_for_boolean_volume is True


def test_small_hole_is_not_watertight_but_repairable():
    mesh = _box_with_small_hole(n_faces_removed=1)
    report = mesh_quality_report(mesh)
    assert report.watertight is False
    assert report.valid_for_signed_distance is False
    assert 0.0 < report.open_boundary_mm <= MAX_AUTO_REPAIR_BOUNDARY_MM

    repaired, was_repaired = repair_small_holes(mesh)
    assert was_repaired is True
    assert repaired.is_watertight is True
    # original must be untouched
    assert mesh.is_watertight is False


def test_large_hole_is_not_auto_repaired():
    # remove an entire face of the box (several triangles) -> boundary loop
    # long enough that it must NOT be silently capped.
    mesh = _box()
    centers = mesh.triangles_center
    keep = centers[:, 2] <= mesh.bounds[1][2] - 1  # drop the whole top face
    mesh.update_faces(keep)
    mesh.remove_unreferenced_vertices()
    report = mesh_quality_report(mesh)
    assert report.open_boundary_mm > MAX_AUTO_REPAIR_BOUNDARY_MM

    result_mesh, was_repaired = repair_small_holes(mesh)
    assert was_repaired is False
    assert result_mesh is mesh  # untouched, returned as-is


def test_disconnected_components_detected_and_gated():
    mesh = _two_disconnected_boxes()
    report = mesh_quality_report(mesh)
    assert report.connected_components == 2
    # even though each piece is individually watertight, multiple shells
    # must not be treated as a single trustworthy signed-distance volume
    assert report.valid_for_signed_distance is False
    assert report.valid_for_boolean_volume is False


def test_self_intersections_reported_as_not_checked():
    report = mesh_quality_report(_box())
    assert report.self_intersections == "not_checked"


def test_signed_distance_sign_convention_inside_positive_outside_negative():
    mesh = _box()
    report = mesh_quality_report(mesh)
    center = mesh.center_mass.reshape(1, 3)
    far_outside = (mesh.bounds[1] + 500).reshape(1, 3)
    result = surface_distance(np.vstack([center, far_outside]), mesh, report)
    assert result["signed"] is True
    assert result["distances"][0] > 0  # inside the box -> positive (room)
    assert result["distances"][1] < 0  # far outside -> negative (conflict)


def test_surface_distance_falls_back_to_unsigned_when_mesh_invalid():
    mesh = _two_disconnected_boxes()  # multiple shells -> not valid for signed distance
    report = mesh_quality_report(mesh)
    assert report.valid_for_signed_distance is False
    query = np.array([[0.0, 0.0, 0.0]])
    result = surface_distance(query, mesh, report)
    assert result["signed"] is False
    assert result["distances"][0] >= 0  # unsigned closest-point distance


def test_bidirectional_distance_small_box_inside_large_box():
    # small box fully inside a large box: from the small box's own surface
    # looking out at the large box (foot->cavity), points sit inside the
    # cavity -> mostly positive. From the large box's surface looking at the
    # small box (cavity->foot), those points are outside the small box ->
    # negative. Directionality genuinely changes the answer.
    small = trimesh.creation.box(extents=[10, 10, 10])
    large = trimesh.creation.box(extents=[100, 100, 100])
    small_q = mesh_quality_report(small)
    large_q = mesh_quality_report(large)

    result = bidirectional_surface_distance(small, small_q, large, large_q)
    assert result["foot_to_cavity"]["signed"] is True
    assert result["cavity_to_foot"]["signed"] is True
    assert np.all(result["foot_to_cavity"]["distances"] > 0)
    assert np.all(result["cavity_to_foot"]["distances"] < 0)


def test_distance_aggregates_negative_and_contact_area():
    # 5 samples, uniform area weight -> total_area = 100 means each sample
    # "represents" 20 of area.
    distances = np.array([-5.0, -0.2, 0.0, 0.3, 10.0])
    agg = distance_aggregates(distances, total_area_mm2=100.0)
    assert agg["min"] == -5.0
    assert agg["max"] == 10.0
    # negative_area = fraction with distance < 0 (2/5) * 100
    assert agg["negative_area_mm2"] == pytest.approx(40.0)
    # contact_area = fraction with |distance| <= 0.5 (3/5: -0.2, 0.0, 0.3) * 100
    assert agg["contact_area_mm2"] == pytest.approx(60.0)


def test_distance_aggregates_empty_input():
    agg = distance_aggregates(np.array([]), total_area_mm2=100.0)
    assert agg["min"] is None
    assert agg["negative_area_mm2"] is None
