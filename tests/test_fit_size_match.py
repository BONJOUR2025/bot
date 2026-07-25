"""Tests for fit_size_match — the size/proportion gate.

Motivated by a real pair: a 250mm foot against a 288mm last produced six zones
of "tightness" and never said the last was two-and-a-half sizes too long. The
gate exists so the cause outranks its symptoms."""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from app.services.fit_size_match import (
    BALL_OFFSET_GATE,
    MIN_GATE_CONFIDENCE,
    SizeMatch,
    evaluate_size_match,
)
from app.services.foot_landmarks import FootLandmarks, Landmark


def _box(width, length, height):
    mesh = trimesh.creation.box(extents=[width, length, height])
    for _ in range(3):
        mesh = mesh.subdivide()
    mesh.apply_translation([0.0, length / 2.0, height / 2.0])
    return mesh


def _landmarks(ball_y, confidence=1.0):
    """Minimal landmark set: only the ball centre and its confidence matter."""
    return FootLandmarks(
        pternion=Landmark("PTERNION", np.array([0.0, 0.0, 20.0]), confidence, "t"),
        plantar_heel_center=Landmark("PLANTAR_HEEL_CENTER", np.array([0.0, 20.0, 2.0]), confidence, "t"),
        mth1=Landmark("MTH1", np.array([40.0, ball_y + 8.0, 10.0]), confidence, "t"),
        mth5=Landmark("MTH5", np.array([-40.0, ball_y - 8.0, 10.0]), confidence, "t"),
        longest_toe_tip=None,
        warnings=[],
    )


def test_well_matched_pair_does_not_trigger_the_gate():
    foot = _box(95, 260, 55)
    cavity = _box(100, 272, 60)        # ~12mm longer: a normal toe allowance
    r = evaluate_size_match(foot, cavity, _landmarks(170.0), _landmarks(172.0))
    assert not r.gate_triggered
    assert r.size_hint is None


def test_far_too_long_last_triggers_the_gate():
    foot = _box(95, 250, 55)
    cavity = _box(100, 288, 60)        # the real failing pair's proportions
    r = evaluate_size_match(foot, cavity, _landmarks(167.0), _landmarks(183.0))
    assert r.gate_triggered
    assert any("toe allowance" in reason for reason in r.reasons)


def test_ball_offset_alone_triggers_the_gate():
    """Same length, but the ball lands well behind the last's own ball."""
    foot = _box(95, 260, 55)
    cavity = _box(100, 272, 60)
    offset = 0.06 * 260               # 6% of foot length, past the 4% gate
    r = evaluate_size_match(foot, cavity, _landmarks(160.0), _landmarks(160.0 + offset))
    assert r.gate_triggered
    assert any("ball line offset" in reason for reason in r.reasons)
    assert abs(r.ball_offset_fraction) > BALL_OFFSET_GATE


def test_ball_offset_is_scaled_by_foot_length():
    """The same millimetre offset must be judged differently on a small and a
    large foot -- that is why the threshold is a fraction."""
    small = evaluate_size_match(_box(95, 230, 55), _box(100, 242, 60),
                                _landmarks(150.0), _landmarks(159.0))
    large = evaluate_size_match(_box(95, 310, 55), _box(100, 322, 60),
                                _landmarks(200.0), _landmarks(209.0))
    assert abs(small.ball_offset_fraction) > abs(large.ball_offset_fraction)


def test_low_landmark_confidence_demotes_the_gate():
    """§21.1: a weak detection must not be allowed to silence the zone
    analysis by declaring the wrong size."""
    foot = _box(95, 250, 55)
    cavity = _box(100, 288, 60)
    weak = MIN_GATE_CONFIDENCE / 2.0
    r = evaluate_size_match(foot, cavity, _landmarks(167.0, weak), _landmarks(183.0, weak))
    assert not r.gate_triggered
    assert any("confidence_too_low" in w for w in r.warnings)


def test_size_hint_points_in_the_right_direction():
    foot = _box(95, 250, 55)
    cavity = _box(100, 288, 60)
    r = evaluate_size_match(foot, cavity, _landmarks(167.0), _landmarks(183.0))
    assert r.size_hint is not None
    assert "меньше" in r.size_hint


def test_functional_clearance_ignores_a_decorative_tip():
    """A long, low, pointed extension past the toe box must not be counted as
    room for toes (§9 of the audit)."""
    foot = _box(95, 250, 55)
    roomy = _box(100, 265, 60)
    base = evaluate_size_match(foot, roomy, _landmarks(167.0), _landmarks(170.0))

    # graft a low decorative spike well past the usable box
    spike = trimesh.creation.box(extents=[20, 40, 6])
    spike.apply_translation([0.0, 285.0, 3.0])
    decorated = trimesh.util.concatenate([roomy, spike])
    with_tip = evaluate_size_match(foot, decorated, _landmarks(167.0), _landmarks(170.0))

    # The 40mm spike must not become 40mm of room for toes. It does shift the
    # answer a little: heights are read over a 12mm band, so the boundary
    # between box and decoration is smeared by about half that. The band is
    # there for robustness on noisy scans, so the tolerance allows for it --
    # what matters is that almost none of the decoration is counted.
    assert with_tip.total_length_excess_mm > base.total_length_excess_mm + 15
    added = with_tip.functional_toe_clearance_mm - base.functional_toe_clearance_mm
    assert added < 8.0, f"decoration leaked {added:.0f}mm into the functional allowance"
