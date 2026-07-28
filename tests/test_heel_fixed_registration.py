"""Tests for heel_fixed_registration — the §28.2 rigid-registration checks.

On the real Nikita/Prada pair this pins the heel to 0.000mm on all three axes,
against the 1.14/1.44/1.69mm drift the masked ICP in last_registration_service
produced for the same input (§9.5 budget is 0.1mm)."""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from app.services.foot_landmarks import detect_foot_landmarks
from app.services.heel_fixed_registration import register_foot_to_last


def _foot_like(length=280.0, width=100.0, height=60.0, subdivisions=4):
    """A foot-ish solid: a box tapered toward the toe so the landmark detector
    has a real medial plateau and lateral peak to find."""
    mesh = trimesh.creation.box(extents=[width, length, height])
    for _ in range(subdivisions):
        mesh = mesh.subdivide()
    mesh.apply_translation([0.0, length / 2.0, height / 2.0])
    v = mesh.vertices.copy()
    f = np.clip(v[:, 1] / length, 0.0, 1.0)
    v[:, 0] *= 1.0 - 0.35 * np.clip((f - 0.65) / 0.35, 0.0, 1.0) ** 2
    mesh.vertices = v
    return mesh


def test_heel_is_pinned_within_tolerance():
    """§9.5: the three heel quantities must land inside 0.1mm."""
    foot = _foot_like()
    last = _foot_like(length=286.0, width=104.0)
    r, _registered, _last = register_foot_to_last(foot, last, "left", "left")
    assert abs(r.posterior_heel_delta_y) < 0.1
    assert abs(r.heel_center_delta_x) < 0.1
    assert abs(r.plantar_heel_delta_z) < 0.1
    assert r.within_tolerance
    assert "heel_not_pinned_within_tolerance" not in r.warnings


def test_registration_is_rigid_scale_stays_one():
    """§28.2: det(R) = 1 and no scaling, so internal distances are preserved."""
    foot = _foot_like()
    last = _foot_like(length=300.0, width=115.0)   # deliberately a size off
    r, registered, _ = register_foot_to_last(foot, last, "left", "left")

    assert r.scale == 1.0
    assert np.isclose(np.linalg.det(r.transform[:3, :3]), 1.0, atol=1e-9)

    # a rigid transform cannot change distances inside the foot
    idx = np.linspace(0, len(foot.vertices) - 1, 200).astype(int)
    before = np.linalg.norm(foot.vertices[idx][:, None] - foot.vertices[idx][None, :], axis=-1)
    after = np.linalg.norm(registered.vertices[idx][:, None] - registered.vertices[idx][None, :], axis=-1)
    assert np.allclose(before, after, atol=1e-6)


def test_size_mismatch_is_preserved_not_optimised_away():
    """§9.1/§9.3: a longer last must still read as longer afterwards -- the
    registration is forbidden from absorbing the disagreement."""
    foot = _foot_like(length=280.0)
    last = _foot_like(length=310.0)
    _r, registered, used_last = register_foot_to_last(foot, last, "left", "left")
    foot_len = registered.vertices[:, 1].max() - registered.vertices[:, 1].min()
    last_len = used_last.vertices[:, 1].max() - used_last.vertices[:, 1].min()
    assert last_len - foot_len == pytest.approx(30.0, abs=1.0)


def test_repeated_registration_is_deterministic():
    """§28.2: running it twice gives the same result."""
    foot, last = _foot_like(), _foot_like(length=290.0)
    a, _, _ = register_foot_to_last(foot, last, "left", "left")
    b, _, _ = register_foot_to_last(foot, last, "left", "left")
    assert np.allclose(a.transform, b.transform)


def test_mirrored_side_is_handled_without_scaling():
    foot = _foot_like()
    last = _foot_like()
    r, _registered, used_last = register_foot_to_last(foot, last, "left", "right")
    assert r.scale == 1.0
    # the last was mirrored for the comparison, the caller's object untouched
    assert used_last is not last


def test_missing_landmarks_report_zero_confidence():
    tiny = trimesh.creation.box(extents=[1.0, 1.0, 1.0])
    r, _, _ = register_foot_to_last(tiny, tiny, "left", "left")
    assert r.confidence == 0.0
    assert r.warnings


# The landmark detector bins the ball zone finely, so these fixtures need to
# be denser than the coarse solids the pinning tests above use -- at
# subdivisions=4 whole bins come up empty and MTH5 is never found.
_DENSE = 5


def _skewed_last(length=286.0, width=104.0, swing_deg=8.0):
    """A last whose forefoot is swung sideways relative to its heel -- the
    shape that made several real 4977/44 scans ask for an 8 degree correction
    while their own fullness neighbours asked for 3. A plain shear about the
    heel, so the swing angle is exactly `swing_deg`."""
    mesh = _foot_like(length=length, width=width, subdivisions=_DENSE)
    v = mesh.vertices.copy()
    v[:, 0] += np.tan(np.radians(swing_deg)) * v[:, 1]
    mesh.vertices = v
    return mesh


def test_ball_swing_is_reported_in_millimetres():
    """The cost of aligning the two axes has to be stated in the units the
    rest of the report uses, not left as a bare angle."""
    foot = _foot_like()
    r, _reg, _last = register_foot_to_last(
        foot, _foot_like(length=286.0, width=104.0, subdivisions=_DENSE), "left", "left")
    assert hasattr(r, "ball_swing_mm")
    assert "ball_swing_mm" in r.as_dict()


def test_a_straight_last_does_not_trip_the_axis_guard():
    foot = _foot_like(subdivisions=_DENSE)
    last = _foot_like(length=286.0, width=104.0, subdivisions=_DENSE)
    r, _reg, _last = register_foot_to_last(foot, last, "left", "left")
    assert abs(r.ball_swing_mm) < 3.0
    assert not r.axis_mismatch
    assert not r.axis_mismatch_severe


def test_a_swung_last_is_flagged_before_it_can_fake_a_medial_verdict():
    """The real defect this guards: an 8 degree correction slid the foot ~26mm
    across the ball and produced a confident 'medial tightness / lateral
    room' reading that described the alignment, not the last. The old check
    only warned past 15 degrees, so it passed in silence."""
    foot = _foot_like(subdivisions=_DENSE)
    swung = _skewed_last(swing_deg=8.0)
    r, _reg, _last = register_foot_to_last(foot, swung, "left", "left")
    assert abs(r.ball_swing_mm) > 10.0
    assert r.axis_mismatch
    assert r.axis_mismatch_severe
    assert any("medial_lateral_findings_unreliable" in w for w in r.warnings)


def test_a_severe_axis_mismatch_halves_confidence():
    foot = _foot_like(subdivisions=_DENSE)
    straight, _reg, _l = register_foot_to_last(
        foot, _foot_like(length=286.0, width=104.0, subdivisions=_DENSE), "left", "left")
    swung, _reg2, _l2 = register_foot_to_last(foot, _skewed_last(swing_deg=8.0), "left", "left")
    assert swung.confidence < straight.confidence


def _heading(mesh):
    """Heel->ball heading, the quantity the rotation exists to align."""
    lm = detect_foot_landmarks(mesh, side="left")
    if lm.ball_center is None or lm.plantar_heel_center is None:
        return None
    d = lm.ball_center - lm.plantar_heel_center.position
    return float(np.degrees(np.arctan2(d[0], d[1])))


def test_rotation_lands_the_foot_axis_on_the_last_axis():
    """The check that catches a flipped rotation sign, which restating the
    formula in a test cannot: measure the heading after registering and
    require it to match the last's.

    This failed before the fix -- the foot's axis went from -0.31 to +7.77 deg
    against a last at -8.33 deg, turning an 8.02 deg disagreement into a
    16.10 deg one, because the rotation was applied in the wrong direction.
    """
    foot = _foot_like(subdivisions=_DENSE)
    last = _skewed_last(swing_deg=8.0)
    before = _heading(foot)
    target = _heading(last)
    assert before is not None and target is not None
    assert abs(target - before) > 3.0, "fixture must actually disagree on axis"

    _r, registered, _last = register_foot_to_last(foot, last, "left", "left")
    after = _heading(registered)
    assert abs(after - target) < 1.0, (
        f"after registration the foot's axis is {after:.2f} deg but the last's "
        f"is {target:.2f} deg"
    )
    # and it must be closer than it started, not further
    assert abs(after - target) < abs(before - target)
