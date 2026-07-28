"""Tests for fit_clearance — §13 (signed/directional clearance), §16 (zones)
and §18 (uncertainty budget). Synthetic geometry, so the classifier can be
driven to every outcome rather than to whatever one real pair happens to be."""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from app.services.fit_clearance import (
    SIGMA_POSE_APPLIED_MM,
    UncertaintyBudget,
    compute_clearance,
)
from app.services.mesh3d_service import mesh_quality_report


def _box(width, length, height, subdivisions=4):
    mesh = trimesh.creation.box(extents=[width, length, height])
    for _ in range(subdivisions):
        mesh = mesh.subdivide()
    mesh.apply_translation([0.0, length / 2.0, height / 2.0])
    return mesh


def _clearance(foot, cavity, **kw):
    return compute_clearance(foot, cavity, mesh_quality_report(cavity), **kw)


def test_roomy_cavity_reads_as_looseness_tight_one_as_tightness():
    """The classifier must be able to reach both verdicts, not just one."""
    foot = _box(90, 260, 60)
    roomy = _box(130, 280, 100)
    tight = _box(66, 280, 100)

    loose_report = _clearance(foot, roomy)
    tight_report = _clearance(foot, tight)

    assert any(z.classification == "LOCAL_LOOSENESS" for z in loose_report.zones)
    assert any(z.classification == "LOCAL_TIGHTNESS" for z in tight_report.zones)


def test_signed_convention_positive_is_room():
    """§13.1: positive = free space, negative = foot outside the cavity."""
    foot = _box(90, 240, 60)
    # nested strictly inside: sharing the Z=0 and Y=0 faces would put those
    # samples exactly on the cavity wall, where the honest clearance is 0
    foot.apply_translation([0.0, 15.0, 15.0])
    roomy = _box(130, 280, 100)
    report = _clearance(foot, roomy)
    assert report.signed
    assert all(z.signed_gap_mm["median"] > 0 for z in report.zones)


def test_required_compression_is_zero_when_nothing_conflicts():
    foot = _box(90, 260, 60)
    roomy = _box(130, 280, 100)
    for z in _clearance(foot, roomy).zones:
        assert z.required_compression_mm["max"] == 0.0
        assert z.conflict_area_mm2 == 0.0


def test_uncertainty_components_add_in_quadrature():
    u = UncertaintyBudget(scan_sigma_mm=3.0, landmark_sigma_mm=4.0,
                          cavity_sigma_mm=0.0, pose_sigma_mm=0.0)
    assert u.total_sigma_mm == pytest.approx(5.0)


def test_pose_inflates_the_uncertainty_budget():
    """§10.4/§13.6: an inferred pose is worth several mm of extra doubt, and
    that must widen the budget rather than be absorbed silently."""
    foot, cavity = _box(90, 260, 60), _box(120, 280, 100)
    without = _clearance(foot, cavity, pose_applied=False)
    with_pose = _clearance(foot, cavity, pose_applied=True)
    assert with_pose.uncertainty.pose_sigma_mm == SIGMA_POSE_APPLIED_MM
    assert with_pose.uncertainty.total_sigma_mm > without.uncertainty.total_sigma_mm
    # and a wider budget must lower confidence, never raise it (§28.7)
    assert max(z.confidence for z in with_pose.zones) <= max(z.confidence for z in without.zones)


def test_conflict_smaller_than_the_noise_is_not_called_tightness():
    """§13.6: 3D scanning resolves ~1mm, so a sub-sigma gap is not a finding."""
    foot = _box(90, 260, 60)
    near_identical = _box(90.4, 280, 100)
    report = _clearance(foot, near_identical)
    assert not any(z.classification == "LOCAL_TIGHTNESS" for z in report.zones)


def test_samples_above_the_cavity_are_excluded_not_counted_as_conflict():
    """§14: a shin sticking out of the shoe is not_evaluable, not tightness."""
    tall_foot = _box(90, 260, 200)   # a "foot" with a long shin
    cavity = _box(120, 280, 90)
    report = _clearance(tall_foot, cavity)
    assert any("not_evaluable" in lim for lim in report.limitations)


def test_report_never_claims_pressure():
    """§11.6/§25.3: without a validated mechanical model the word is banned."""
    report = _clearance(_box(90, 260, 60), _box(120, 280, 100))
    blob = str(report.as_dict()).lower()
    assert "pressure" not in blob or "no pressure is computed" in blob
    assert any("no pressure" in lim for lim in report.limitations)


def test_proxy_cavity_is_declared_a_limitation():
    report = _clearance(_box(90, 260, 60), _box(120, 280, 100), cavity_mode="LAST_PROXY")
    assert report.cavity_mode == "LAST_PROXY"
    assert any("not a measured shoe interior" in lim for lim in report.limitations)


def test_directional_clearance_is_split_by_facing_not_by_coordinate_sign():
    """§13.2: a point at x>0 whose surface faces up is dorsal, not medial."""
    foot = _box(90, 260, 60)
    # cavity much taller than wide -> room above, pinch at the sides
    cavity = _box(80, 280, 160)
    report = _clearance(foot, cavity)
    ball = next((z for z in report.zones if z.name == "ball"), None)
    assert ball is not None
    d = ball.directional_mm
    assert d["dorsal"] is not None and d["medial"] is not None
    assert d["dorsal"] > d["medial"]   # roomy above, tight across


def _last_with_cone(width=100.0, length=290.0, body_height=60.0,
                    cone_height=100.0, cone_frac=0.25, subdivisions=5):
    """A last shape: a shoe-sized body with a narrow mounting cone rising well
    above it, which is what a real scanned last looks like.

    Built by deforming one box rather than gluing two together: overlapping
    solids concatenate into a self-intersecting mesh, which
    mesh_quality_report rejects for signed distance, and the whole comparison
    then falls back to unsigned distance where nothing can ever read as tight.
    """
    mesh = trimesh.creation.box(extents=[width, length, cone_height])
    for _ in range(subdivisions):
        mesh = mesh.subdivide()
    v = mesh.vertices.copy()
    z0 = v[:, 2].min()
    above = (v[:, 2] - z0) > body_height
    # taper the part above the body inward, in both x and y, into a cone
    t = np.clip(((v[:, 2] - z0) - body_height) / (cone_height - body_height), 0, 1)
    scale = np.where(above, 1.0 - (1.0 - cone_frac) * t, 1.0)
    v[:, 0] *= scale
    v[:, 1] *= scale
    mesh.vertices = v
    mesh.apply_translation([0.0, length / 2.0, cone_height / 2.0])
    mesh.apply_translation([0.0, 0.0, -mesh.vertices[:, 2].min()])
    return mesh


def test_the_cone_last_fixture_supports_signed_distance():
    """Guards the fixture itself: if the cavity is not usable for signed
    distance the comparison silently falls back to unsigned, where no zone can
    ever read as tight and the two tests below would pass for no reason."""
    assert mesh_quality_report(_last_with_cone()).valid_for_signed_distance


def test_ankle_above_the_shoe_is_not_counted_as_a_conflict():
    """The defect a real fitting exposed: the cut-off used the cavity's single
    highest point, which on a last is the top of its mounting cone, so the
    foot's ankle was compared against the last's waist and reported as a
    conflict. A wearer found that pair loose everywhere.

    Here the foot sits comfortably inside the shoe body, but its leg rises far
    above it -- nothing should read as tight.
    """
    foot = _box(80, 280, 50)
    leg = trimesh.creation.box(extents=[70, 55, 130])
    leg.apply_translation([0.0, 42.0, 65.0])
    foot = trimesh.util.concatenate([foot, leg])

    r = _clearance(foot, _last_with_cone())
    tight = [z.name for z in r.zones if z.classification == "LOCAL_TIGHTNESS"]
    assert not tight, f"ankle/leg above the shoe read as tightness in {tight}"


def test_a_foot_wider_than_the_cavity_is_still_reported():
    """The exclusion must not swallow real conflicts: a foot jutting out
    sideways past the cavity wall, at shoe height, is a genuine finding."""
    r = _clearance(_box(130, 280, 50), _last_with_cone(width=95.0))
    tight = [z.name for z in r.zones if z.classification == "LOCAL_TIGHTNESS"]
    assert tight, "a foot wider than the cavity produced no tightness at all"
