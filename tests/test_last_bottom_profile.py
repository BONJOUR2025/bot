"""Tests for last_bottom_profile — synthetic geometry only.

Real-data validation against the Prada 43 last (heel_height ~23.1mm,
toe_spring_tip ~36.3mm, profile 80-95% ~11.3/15.1/17.4/21.9mm, all from the
source spec) was done ad hoc against the actual uploaded file during
development, not committed here — see the module's own docstring/plan notes
for that discovery (the naive tip reading needs the *exact* extreme vertex,
not a banded percentile, which last_pose_measurements.py implements)."""
from __future__ import annotations

import numpy as np
import trimesh
import pytest

from app.services.last_bottom_profile import (
    extract_bottom_profile,
    find_ground_plane,
    profile_z_at_y,
)


def _flat_bottom_box(width=100, length=280, height=90):
    mesh = trimesh.creation.box(extents=[width, length, height])
    for _ in range(6):
        mesh = mesh.subdivide()
    mesh.apply_translation([0.0, length / 2.0, height / 2.0])
    return mesh


def test_find_ground_plane_flat_box_high_confidence():
    mesh = _flat_bottom_box()
    gp = find_ground_plane(mesh)
    assert gp.ground_z == pytest.approx(0.0, abs=0.5)
    assert gp.angle_to_vertical_deg < 1.0
    assert gp.confidence > 0.95


def test_find_ground_plane_tilted_gives_lower_confidence():
    flat = find_ground_plane(_flat_bottom_box())
    mesh = _flat_bottom_box()
    # tilt the whole object -- the bottom is no longer horizontal, so the
    # fit angle should pick that up and confidence should drop relative to
    # the flat case (comparative, not an absolute cutoff -- percentile-based
    # low-Z selection on a tilted box doesn't cleanly isolate the whole
    # bottom face, so the *measured* angle is a fraction of the true tilt;
    # the direction of the effect is what matters here).
    rot = trimesh.transformations.rotation_matrix(np.radians(25), [1, 0, 0])
    mesh.apply_transform(rot)
    tilted = find_ground_plane(mesh)
    assert tilted.angle_to_vertical_deg > flat.angle_to_vertical_deg + 2.0
    assert tilted.confidence < flat.confidence


def test_extract_bottom_profile_flat_box_is_near_zero():
    mesh = _flat_bottom_box()
    profile = extract_bottom_profile(mesh)
    assert len(profile) > 50
    z_vals = [p["z"] for p in profile]
    assert max(abs(z) for z in z_vals) < 1.0


class _FakeMesh:
    """extract_bottom_profile only ever reads `.vertices` -- a bare
    point cloud is enough and, unlike a solid box, doesn't have full-height
    vertical side walls contaminating the per-Y-band low-percentile read
    (a real box's side faces span the entire Z range at every Y, which a
    plain P2-percentile-per-bin approach can't distinguish from the actual
    bottom surface; a real foot/last doesn't have that pathology, and
    neither should this fixture)."""

    def __init__(self, vertices: np.ndarray):
        self.vertices = vertices


def _sloped_sole_point_cloud(length=280.0, height_front_extra=30.0, n=20000, shell_mm=3.0, seed=0):
    """A thin shell of points hugging a linearly-rising bottom surface --
    Z_bottom(Y) = (Y/length) * height_front_extra -- standing in for a
    last's actual sole surface without the box-fixture pathology above."""
    rng = np.random.default_rng(seed)
    y = rng.uniform(0.0, length, n)
    z_bottom = (y / length) * height_front_extra
    z = z_bottom + rng.uniform(0.0, shell_mm, n)
    x = rng.uniform(-40.0, 40.0, n)
    return _FakeMesh(np.column_stack([x, y, z]))


def test_extract_bottom_profile_tracks_linear_slope():
    length = 280.0
    height_front_extra = 30.0
    mesh = _sloped_sole_point_cloud(length=length, height_front_extra=height_front_extra)
    profile = extract_bottom_profile(mesh)
    z_back = profile_z_at_y(profile, 5.0)
    z_mid = profile_z_at_y(profile, length / 2.0)
    z_front = profile_z_at_y(profile, length - 5.0)
    assert z_back == pytest.approx(0.0, abs=2.0)
    assert z_mid == pytest.approx(height_front_extra / 2.0, abs=3.0)
    assert z_front == pytest.approx(height_front_extra, abs=3.0)
    # monotonic rise, matching the linear shear applied
    assert z_back < z_mid < z_front


def test_profile_z_at_y_interpolates_between_samples():
    profile = [{"y": 0.0, "z": 0.0}, {"y": 10.0, "z": 10.0}, {"y": 20.0, "z": 20.0}]
    assert profile_z_at_y(profile, 5.0) == pytest.approx(5.0)
    assert profile_z_at_y(profile, 15.0) == pytest.approx(15.0)


def test_profile_z_at_y_empty_profile_returns_none():
    assert profile_z_at_y([], 5.0) is None
