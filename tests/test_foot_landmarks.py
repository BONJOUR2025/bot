"""Tests for foot_landmarks — the §28.3 landmark checks. Synthetic geometry
only; on the real Nikita scan this locates MTH1 at 70.6% and MTH5 at 63.1% of
foot length with a 21.0mm ball obliquity (textbook range 15-30mm), against the
single 198.9mm `ball_y` the old scalar API returned."""
from __future__ import annotations

import numpy as np
import pytest

from app.services.foot_landmarks import detect_foot_landmarks


class _FakeMesh:
    def __init__(self, vertices: np.ndarray):
        self.vertices = vertices


def _foot_cloud(length=280.0, n=60000, seed=0,
                mth1_frac=0.72, mth5_frac=0.62, hallux_bulge=True):
    """A left-foot-like outline: the lateral edge peaks at `mth5_frac` and
    recedes; the medial edge grows to a plateau at `mth1_frac` and (optionally)
    keeps growing into a hallux bulge near the toes -- the shape that makes a
    plain argmax pick the big toe instead of MTH1."""
    rng = np.random.default_rng(seed)
    y = rng.uniform(0.0, length, n)
    f = y / length

    # medial half-width: rises to a plateau at mth1_frac, then hallux bulge
    medial = 30.0 + 22.0 * np.clip(f / mth1_frac, 0.0, 1.0)
    if hallux_bulge:
        extra = np.clip((f - 0.80) / 0.12, 0.0, 1.0) * 3.0
        extra *= np.clip((0.95 - f) / 0.05, 0.0, 1.0)
        medial = medial + extra
    # lateral half-width: a genuine peak at mth5_frac
    lateral = 30.0 + 20.0 * np.exp(-((f - mth5_frac) ** 2) / (2 * 0.16 ** 2))
    lateral *= np.clip((1.02 - f) / 0.25, 0.15, 1.0)

    side = rng.integers(0, 2, n)
    x = np.where(side == 1, medial * rng.uniform(0.97, 1.0, n),
                 -lateral * rng.uniform(0.97, 1.0, n))
    z = rng.uniform(0.0, 28.0, n)
    return _FakeMesh(np.column_stack([x, y, z])), length


def test_mth1_and_mth5_are_independent_points_not_one_ball_y():
    """§4.3: the two heads are separate 3D points with different Y."""
    mesh, length = _foot_cloud()
    lm = detect_foot_landmarks(mesh, side="left")
    assert lm.mth1 is not None and lm.mth5 is not None
    assert lm.mth1.position[1] != lm.mth5.position[1]
    assert lm.ball_obliquity_mm() > 5.0
    # and they are on opposite sides
    assert lm.mth1.position[0] > 0 > lm.mth5.position[0]


def test_mth1_is_not_dragged_onto_the_hallux():
    """The failure this detector was rewritten for: with a hallux bulge more
    medial than the ball, a plain argmax lands on the big toe."""
    mesh, length = _foot_cloud(hallux_bulge=True)
    lm = detect_foot_landmarks(mesh, side="left")
    frac = lm.mth1.position[1] / length
    assert 0.55 < frac < 0.82, f"MTH1 at {frac:.0%} of length looks like the hallux"


def test_mth5_lands_on_the_lateral_peak():
    mesh, length = _foot_cloud(mth5_frac=0.62)
    lm = detect_foot_landmarks(mesh, side="left")
    assert lm.mth5.position[1] / length == pytest.approx(0.62, abs=0.08)


def test_right_foot_mirrors_the_medial_direction():
    mesh, _ = _foot_cloud()
    mirrored = _FakeMesh(mesh.vertices * np.array([-1.0, 1.0, 1.0]))
    lm = detect_foot_landmarks(mirrored, side="right")
    # for a right foot the medial side is -X, so MTH1 must come out negative
    assert lm.mth1.position[0] < 0 < lm.mth5.position[0]


def test_unknown_side_is_flagged():
    mesh, _ = _foot_cloud()
    lm = detect_foot_landmarks(mesh, side=None)
    assert "foot_side_unknown_medial_direction_assumed" in lm.warnings


def test_pternion_and_plantar_heel_are_distinct():
    """§28.3: pternion must not coincide with the plantar heel centre."""
    mesh, _ = _foot_cloud()
    lm = detect_foot_landmarks(mesh, side="left")
    assert lm.pternion is not None and lm.plantar_heel_center is not None
    assert not np.allclose(lm.pternion.position, lm.plantar_heel_center.position)
    assert "pternion_coincides_with_plantar_heel" not in lm.warnings


def test_sparse_mesh_refuses_rather_than_guessing():
    lm = detect_foot_landmarks(_FakeMesh(np.zeros((10, 3))))
    assert lm.confidence == 0.0
    assert "mesh_too_sparse" in lm.warnings


def test_positions_are_not_reported_to_false_precision():
    """§26.18: no hundredths of a millimetre on a landmark uncertain by mm."""
    mesh, _ = _foot_cloud()
    d = detect_foot_landmarks(mesh, side="left").as_dict()
    for coord in d["mth1"]["position_mm"]:
        assert round(coord, 1) == coord
