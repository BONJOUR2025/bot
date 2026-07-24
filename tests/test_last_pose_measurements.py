"""Tests for last_pose_measurements — synthetic geometry per the spec's own
§26.1/§26.2 test descriptions. Real-data validation against the Prada 43
last (heel_height/toe_spring_tip within ~0.4mm of the spec's 23.1/36.3mm,
the residual being this module's own measured ground_z=0.373mm rather than
an assumed exact 0) was done ad hoc during development -- see
last_pose_measurements.py's module docstring."""
from __future__ import annotations

import numpy as np
import pytest

from app.services.last_bottom_profile import extract_bottom_profile
from app.services.last_pose_measurements import measure_heel_toe


class _FakeMesh:
    def __init__(self, vertices: np.ndarray):
        self.vertices = vertices


def _rear_endpoint_last(length=280.0, rear_z=25.0, n=20000, seed=1):
    """§26.1: ground Z=0, rear endpoint Z=25 -> heel_height should be 25."""
    rng = np.random.default_rng(seed)
    y = rng.uniform(0.0, length, n)
    # a shallow, mostly-flat sole that happens to end at rear_z exactly at y=0
    z_bottom = rear_z * np.exp(-y / 6.0)  # decays quickly away from the heel
    z = z_bottom + rng.uniform(0.0, 1.0, n)
    x = rng.uniform(-40.0, 40.0, n)
    vertices = np.column_stack([x, y, z])
    # force the exact rear vertex (min Y) to have Z == rear_z precisely,
    # matching how measure_heel_toe reads the endpoint (exact extreme vertex).
    rear_idx = np.argmin(y)
    vertices[rear_idx, 2] = rear_z
    return _FakeMesh(vertices)


def test_heel_height_matches_rear_endpoint():
    mesh = _rear_endpoint_last(rear_z=25.0)
    profile = extract_bottom_profile(mesh)
    result = measure_heel_toe(mesh, profile, ground_z=0.0)
    assert result["heel_height_endpoint_mm"] == pytest.approx(25.0, abs=0.01)


def _toe_spring_last(length=280.0, rise_start_frac=0.80, tip_z=30.0, n=20000, seed=2):
    """§26.2: Z(Y) flat (0) up to 80%, then linear rise to 30mm at the tip."""
    rng = np.random.default_rng(seed)
    y = rng.uniform(0.0, length, n)
    rise_start_y = rise_start_frac * length
    frac_past_rise = np.clip((y - rise_start_y) / (length - rise_start_y), 0.0, 1.0)
    z_bottom = frac_past_rise * tip_z
    z = z_bottom + rng.uniform(0.0, 0.5, n)
    x = rng.uniform(-40.0, 40.0, n)
    vertices = np.column_stack([x, y, z])
    tip_idx = np.argmax(y)
    vertices[tip_idx, 2] = tip_z
    return _FakeMesh(vertices), rise_start_y


def test_toe_spring_tip_and_profile_fractions():
    length = 280.0
    tip_z = 30.0
    mesh, rise_start_y = _toe_spring_last(length=length, rise_start_frac=0.80, tip_z=tip_z)
    profile = extract_bottom_profile(mesh)
    result = measure_heel_toe(mesh, profile, ground_z=0.0)

    assert result["toe_spring_tip_mm"] == pytest.approx(tip_z, abs=0.5)
    # 85/90/95% are all past the 80% rise start -> proportionally risen
    expected_85 = (0.85 * length - rise_start_y) / (length - rise_start_y) * tip_z
    expected_90 = (0.90 * length - rise_start_y) / (length - rise_start_y) * tip_z
    expected_95 = (0.95 * length - rise_start_y) / (length - rise_start_y) * tip_z
    assert result["toe_spring_85"] == pytest.approx(expected_85, abs=1.5)
    assert result["toe_spring_90"] == pytest.approx(expected_90, abs=1.5)
    assert result["toe_spring_95"] == pytest.approx(expected_95, abs=1.5)
    # 80% itself should be near zero (right at the rise start)
    assert result["toe_spring_80"] == pytest.approx(0.0, abs=2.0)


def test_heel_seat_mean_lower_than_endpoint_when_seat_slopes_away():
    # rear endpoint is a sharp peak (25mm) that decays fast -- the "seat"
    # region mean should be noticeably lower than the endpoint, exactly the
    # distinction the spec asks these two fields to capture (§7.3).
    mesh = _rear_endpoint_last(rear_z=25.0)
    profile = extract_bottom_profile(mesh)
    result = measure_heel_toe(mesh, profile, ground_z=0.0)
    assert result["heel_seat_mean_height_mm"] < result["heel_height_endpoint_mm"] - 5.0
