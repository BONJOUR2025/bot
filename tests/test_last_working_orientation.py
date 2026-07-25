"""Tests for last_working_orientation — §6/§10.2 and the §28.4 orientation
test list. Synthetic geometry only; the real-data finding that motivated this
module (the Prada 43 last measures 22.7mm by the rearmost vertex but has an
effective elevation of ~0.1mm, because its heel seat and ball tread both rest
on the support plane) is recorded in the module docstring."""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from app.services.last_working_orientation import estimate_working_orientation


class _FakeMesh:
    """estimate_working_orientation only reads `.vertices`."""

    def __init__(self, vertices: np.ndarray):
        self.vertices = vertices


def _last_point_cloud(length=280.0, heel_lift=0.0, n=60000, seed=0):
    """A last-like shell: a heel seat patch and a ball tread patch resting on
    the support plane, an arch lifted between them, and a toe spring rising at
    the front. `heel_lift` raises the heel seat, i.e. it IS the effective
    elevation the module should recover."""
    rng = np.random.default_rng(seed)
    y = rng.uniform(0.0, length, n)
    f = y / length
    z = np.empty_like(y)

    heel = f <= 0.16
    arch = (f > 0.16) & (f < 0.50)
    ball = (f >= 0.50) & (f <= 0.68)
    front = f > 0.68

    z[heel] = heel_lift
    # arch bulges up between the two support patches
    t = (f[arch] - 0.16) / (0.50 - 0.16)
    z[arch] = heel_lift * (1 - t) + 6.0 * np.sin(np.pi * t)
    z[ball] = 0.0
    z[front] = 30.0 * ((f[front] - 0.68) / 0.32) ** 2  # toe spring

    z = z + rng.uniform(0.0, 0.4, n)  # thin shell noise
    x = rng.uniform(-40.0, 40.0, n)
    return _FakeMesh(np.column_stack([x, y, z]))


def test_flat_last_reports_near_zero_elevation():
    mesh = _last_point_cloud(heel_lift=0.0)
    r = estimate_working_orientation(mesh)
    assert r.effective_heel_elevation_mm == pytest.approx(0.0, abs=1.0)
    assert r.orientation_confidence > 0.5
    assert not r.warnings


def test_heeled_last_recovers_its_elevation():
    mesh = _last_point_cloud(heel_lift=25.0)
    r = estimate_working_orientation(mesh)
    assert r.effective_heel_elevation_mm == pytest.approx(25.0, abs=1.5)


def test_heel_support_is_found_behind_ball_support():
    """§28.4: heel support must sit behind ball support."""
    mesh = _last_point_cloud(heel_lift=12.0)
    r = estimate_working_orientation(mesh)
    assert r.heel_support is not None and r.ball_support is not None
    assert r.heel_support.fraction_range[0] < r.ball_support.fraction_range[0]


def test_elevation_ignores_a_tall_rear_wall():
    """The whole point of the module: a last whose rearmost vertices are far
    above the support plane (the curved back of the heel) must NOT report that
    height as a heel elevation."""
    mesh = _last_point_cloud(heel_lift=0.0)
    v = mesh.vertices
    # graft on a near-vertical back wall rising to 25mm at the very rear
    wall = np.column_stack([
        np.random.default_rng(1).uniform(-30, 30, 800),
        np.random.default_rng(2).uniform(-2.0, 2.0, 800),
        np.random.default_rng(3).uniform(0.0, 25.0, 800),
    ])
    tall = _FakeMesh(np.vstack([v, wall]))
    r = estimate_working_orientation(tall)
    assert r.effective_heel_elevation_mm < 2.0
    assert float(tall.vertices[np.argmin(tall.vertices[:, 1]), 2]) > 5.0  # rear vertex IS high


def test_maker_value_overrides_measurement_and_flags_disagreement():
    """§6.2: the manufacturer's figure wins, but a large disagreement with the
    measured support geometry has to be surfaced, not silently swallowed."""
    mesh = _last_point_cloud(heel_lift=0.0)
    r = estimate_working_orientation(mesh, maker_heel_height_mm=30.0)
    assert r.effective_heel_elevation_mm == pytest.approx(30.0)
    assert "maker_heel_height_disagrees_with_measurement" in r.warnings


def test_flat_slab_measures_zero_elevation():
    """A flat object (e.g. a foot scanned on a plane) has both seats at the
    same height, so the elevation is 0 -- which is the safe answer: the pose
    stage then applies no rotation at all."""
    rng = np.random.default_rng(0)
    n = 20000
    y = rng.uniform(0.0, 260.0, n)
    flat = _FakeMesh(np.column_stack([
        rng.uniform(-40, 40, n), y, rng.uniform(0.0, 0.5, n),
    ]))
    r = estimate_working_orientation(flat)
    assert r.effective_heel_elevation_mm == pytest.approx(0.0, abs=0.5)


def test_degenerate_input_refuses_rather_than_guessing():
    tiny = _FakeMesh(np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [2.0, 2.0, 0.5]]))
    r = estimate_working_orientation(tiny)
    assert r.orientation_confidence == 0.0
    assert r.effective_heel_elevation_mm == 0.0
    assert r.warnings
