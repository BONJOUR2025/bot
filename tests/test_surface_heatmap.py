"""Tests for surface_heatmap — synthetic geometry only. Real-data validation
(vertex colors round-trip through GLB export/import with a wide, non-flat
color range on the real Nikita/Prada pair) was done ad hoc during
development, not committed here."""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from app.services.surface_heatmap import (
    LOOSE_RGB,
    NEUTRAL_RGB,
    TIGHT_RGB,
    ease_to_vertex_colors,
    vertex_ease_values,
)


def _dense_box(width=90, length=270, height=60):
    mesh = trimesh.creation.box(extents=[width, length, height])
    for _ in range(4):
        mesh = mesh.subdivide()
    mesh.apply_translation([0.0, length / 2.0, height / 2.0])
    return mesh


def test_vertex_ease_values_no_smoothing_matches_nearest_sample():
    mesh = _dense_box()
    # One sample point per vertex, each carrying its own vertex index as
    # the "distance" -- with smoothing off, every vertex should map back
    # to its own value exactly (nearest sample IS itself).
    sample_points = mesh.vertices
    sample_distances = np.arange(len(mesh.vertices), dtype=np.float64)
    values = vertex_ease_values(mesh, sample_points, sample_distances, smooth_passes=0)
    assert np.allclose(values, sample_distances)


def test_vertex_ease_values_smoothing_pulls_outliers_toward_neighbors():
    mesh = _dense_box()
    n = len(mesh.vertices)
    sample_points = mesh.vertices
    sample_distances = np.zeros(n)
    spike_idx = 0
    sample_distances[spike_idx] = 100.0  # one extreme outlier vertex
    smoothed = vertex_ease_values(mesh, sample_points, sample_distances, smooth_passes=3)
    # the spike itself should shrink after averaging with its (zero-valued) neighbors
    assert 0.0 < smoothed[spike_idx] < 100.0
    # a direct neighbor should have picked up some of the spike's value
    neighbor = mesh.vertex_neighbors[spike_idx][0]
    assert smoothed[neighbor] > 0.0


def test_vertex_ease_values_handles_no_finite_distances():
    mesh = _dense_box()
    sample_points = mesh.vertices
    sample_distances = np.full(len(mesh.vertices), np.nan)
    values = vertex_ease_values(mesh, sample_points, sample_distances)
    assert np.all(values == 0.0)


def test_ease_to_vertex_colors_extremes_and_neutral():
    ease = np.array([-100.0, 0.0, 100.0])
    colors = ease_to_vertex_colors(ease, clamp_mm=6.0)
    assert colors.shape == (3, 4)
    assert tuple(colors[0, :3]) == TIGHT_RGB
    assert tuple(colors[1, :3]) == NEUTRAL_RGB
    assert tuple(colors[2, :3]) == LOOSE_RGB
    assert np.all(colors[:, 3] == 255)


def test_ease_to_vertex_colors_interpolates_between_neutral_and_extremes():
    ease = np.array([-3.0, 3.0])  # half of the default 6mm clamp
    colors = ease_to_vertex_colors(ease, clamp_mm=6.0)
    tight_mid = colors[0, :3].astype(float)
    loose_mid = colors[1, :3].astype(float)
    neutral = np.array(NEUTRAL_RGB, dtype=float)
    tight = np.array(TIGHT_RGB, dtype=float)
    loose = np.array(LOOSE_RGB, dtype=float)
    assert tight_mid == pytest.approx((neutral + tight) / 2, abs=2.0)
    assert loose_mid == pytest.approx((neutral + loose) / 2, abs=2.0)
