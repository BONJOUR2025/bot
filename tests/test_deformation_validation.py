"""Tests for deformation_validation — identity-deformation sanity checks
(no deformation at all should read as a perfect result) plus a distorted
mesh case to confirm the metrics actually move when geometry changes."""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from app.services.deformation_validation import validate_deformation


def _dense_box(width=90, length=270, height=60):
    mesh = trimesh.creation.box(extents=[width, length, height])
    for _ in range(4):
        mesh = mesh.subdivide()
    mesh.apply_translation([0.0, length / 2.0, height / 2.0])
    return mesh


def test_identity_deformation_reports_perfect_quality():
    mesh = _dense_box()
    quality = validate_deformation(mesh, mesh.copy())
    assert quality["mean_edge_strain"] == 0.0
    assert quality["p95_edge_strain"] == 0.0
    assert quality["area_ratio"] == 1.0
    assert quality["volume_ratio"] == 1.0
    assert quality["flipped_face_fraction"] == 0.0
    assert quality["self_intersections"] == "not_checked"


def test_uniform_scale_up_changes_area_and_volume_ratio_but_no_strain_uniformly():
    mesh = _dense_box()
    scaled = mesh.copy()
    scaled.vertices = scaled.vertices * 1.1  # uniform scale from the origin
    quality = validate_deformation(mesh, scaled)
    # a uniform scale stretches every edge by the same factor -- strain is
    # nonzero but uniform (mean ~= p95), area/volume ratios move accordingly.
    assert quality["mean_edge_strain"] > 0.05
    assert quality["mean_edge_strain"] == pytest.approx(quality["p95_edge_strain"], rel=0.2)
    assert quality["area_ratio"] > 1.15  # area scales with the square of length
    assert quality["volume_ratio"] > 1.3  # volume scales with the cube of length
    assert quality["flipped_face_fraction"] == 0.0


def test_local_bulge_produces_nonzero_but_bounded_strain_and_no_flips():
    mesh = _dense_box()
    deformed = mesh.copy()
    v = deformed.vertices
    y = v[:, 1]
    length = float(y.max())
    # push a middle band outward in Z a bit -- a real but mild local
    # distortion, not a fold-over.
    band = np.abs(y - length / 2.0) < length * 0.1
    v2 = v.copy()
    v2[band, 2] += 8.0
    deformed.vertices = v2
    quality = validate_deformation(mesh, deformed)
    assert quality["mean_edge_strain"] > 0.0
    assert quality["p95_edge_strain"] >= quality["mean_edge_strain"]
    assert quality["flipped_face_fraction"] < 0.05
