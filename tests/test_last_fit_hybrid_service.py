"""Tests for last_fit_hybrid_service — synthetic points/meshes only."""
from __future__ import annotations

import numpy as np
import trimesh
import pytest

from app.services.last_fit_hybrid_service import (
    BILATERAL_LAST_MISMATCH,
    FOREFOOT_TAPER_TOO_FAST,
    LEFT_FOOT_DOMINANT,
    MISALLOCATED_VOLUME,
    NARROW_HIGH,
    RIGHT_FOOT_DOMINANT,
    WIDE_LOW,
    _classify_zone_pattern,
    _critical_sections,
    _cross_zone_patterns,
    _forefoot_taper_too_fast,
    _risk_scores,
    _zone_directional_summary,
    combine_bilateral,
    compare_hybrid,
)


def _risks(tightness=0.0, looseness=0.0):
    return {"risks": {"tightness_risk": tightness, "looseness_risk": looseness, "retention_risk": 0.0}}


def _points_with_normals(n=40, y=150.0):
    """20 side-wall-like points (normals +-X) and 20 top/bottom-like points
    (normals +-Z), all in the same zone -- lets a test assign each group its
    own distance value and check the summary keeps them separate."""
    rng = np.random.default_rng(3)
    half = n // 2
    points = np.column_stack([rng.uniform(-45, 45, n), np.full(n, y), rng.uniform(0, 60, n)])
    normals = np.zeros((n, 3))
    # first half: horizontal-facing (medial x>=0 half, lateral x<0 half)
    normals[:half // 2] = [1.0, 0.0, 0.0]
    normals[half // 2:half] = [-1.0, 0.0, 0.0]
    # second half: vertical-facing (dorsal +z half, plantar -z half)
    normals[half:half + (n - half) // 2] = [0.0, 0.0, 1.0]
    normals[half + (n - half) // 2:] = [0.0, 0.0, -1.0]
    return points, normals


def test_zone_directional_summary_splits_medial_lateral_dorsal_plantar():
    points, normals = _points_with_normals()
    # medial (normal +x) forced tight, lateral (normal -x) forced loose,
    # dorsal (normal +z) forced loose, plantar (normal -z) forced tight.
    distances = np.select(
        [
            (normals[:, 0] >= 0.5),
            (normals[:, 0] <= -0.5),
            (normals[:, 2] >= 0.5),
            (normals[:, 2] <= -0.5),
        ],
        [-5.0, 5.0, 6.0, -6.0],
    )
    summary = _zone_directional_summary(points, normals, distances, 0.5, 0.6, foot_length_mm=270.0)
    assert summary is not None
    assert summary["medial_clearance_mm"] == pytest.approx(-5.0)
    assert summary["lateral_clearance_mm"] == pytest.approx(5.0)
    assert summary["dorsal_clearance_mm"] == pytest.approx(6.0)
    assert summary["plantar_clearance_mm"] == pytest.approx(-6.0)


def test_classify_zone_pattern_narrow_high():
    directional = {"medial_clearance_mm": -5.0, "lateral_clearance_mm": -3.0,
                   "dorsal_clearance_mm": 6.0, "plantar_clearance_mm": 1.0}
    assert _classify_zone_pattern("ball", directional) == NARROW_HIGH


def test_classify_zone_pattern_wide_low():
    directional = {"medial_clearance_mm": 6.0, "lateral_clearance_mm": 5.0,
                   "dorsal_clearance_mm": -4.0, "plantar_clearance_mm": 1.0}
    assert _classify_zone_pattern("ball", directional) == WIDE_LOW


def test_classify_zone_pattern_none_when_all_ideal():
    directional = {"medial_clearance_mm": 1.0, "lateral_clearance_mm": 1.0,
                   "dorsal_clearance_mm": 1.0, "plantar_clearance_mm": 1.0}
    assert _classify_zone_pattern("ball", directional) is None


def test_classify_zone_pattern_ignores_height_in_heel_and_waist():
    # Same "narrow + tall" numbers that trigger NARROW_HIGH in the ball zone
    # must NOT trigger it in heel/waist -- that dorsal reading there is
    # shin/ankle contamination, not a real dorsal void (see
    # _ZONE_HEIGHT_MATTERS).
    directional = {"medial_clearance_mm": -5.0, "lateral_clearance_mm": -3.0,
                   "dorsal_clearance_mm": 6.0, "plantar_clearance_mm": 1.0}
    assert _classify_zone_pattern("heel", directional) is None
    assert _classify_zone_pattern("waist", directional) is None


def test_cross_zone_general_oversize():
    width_ease = {k: 8.0 for k in ("heel", "waist", "instep", "ball", "toe")}
    assert "GENERAL_OVERSIZE" in _cross_zone_patterns(width_ease)


def test_risk_scores_bounded_and_directional():
    tight_zones = {"ball": -8.0, "instep": -6.0}
    tightness, looseness = _risk_scores(tight_zones)
    assert 0.0 <= tightness <= 1.0
    assert looseness == 0.0
    assert tightness > 0.0


def _dense_box(width, length, height):
    mesh = trimesh.creation.box(extents=[width, length, height])
    for _ in range(5):
        mesh = mesh.subdivide()
    mesh.apply_translation([0.0, length / 2.0, height / 2.0])
    return mesh


def test_compare_hybrid_end_to_end_detects_narrow_high():
    # cavity narrower AND taller than the foot -> foot's surface pokes out
    # medially/laterally (tight) while there's extra room above (dorsal void).
    foot = _dense_box(width=90, length=270, height=60)
    cavity = _dense_box(width=80, length=282, height=75)

    result = compare_hybrid(foot, "left", cavity, "left")
    assert result["engine"] == "hybrid_v2"
    assert set(result["zones"].keys()) == {"heel", "waist", "instep", "ball", "toe"}
    assert 0.0 <= result["risks"]["tightness_risk"] <= 1.0
    assert 0.0 <= result["risks"]["looseness_risk"] <= 1.0
    assert 0.0 <= result["risks"]["retention_risk"] <= 1.0
    # a uniform narrower+taller cavity should show up as NARROW_HIGH somewhere
    patterns_found = {p["pattern"] for p in result["patterns"]}
    assert NARROW_HIGH in patterns_found


def test_compare_hybrid_end_to_end_detects_wide_low():
    # A modest height gap (75 -> 68, not 60) keeps the foot's medial/lateral
    # side-wall points within the cavity's own height range -- too large a
    # gap and some of those points' nearest cavity point "wraps" to the
    # cavity's top edge instead of its side wall, contaminating the
    # medial/lateral read with what's really a dorsal signal.
    foot = _dense_box(width=90, length=270, height=75)
    cavity = _dense_box(width=110, length=282, height=68)

    result = compare_hybrid(foot, "left", cavity, "left")
    patterns_found = {p["pattern"] for p in result["patterns"]}
    assert WIDE_LOW in patterns_found


def test_compare_hybrid_applies_automatic_pose_when_last_metadata_missing():
    # Since foot_pose_deformation.resolve_foot_pose was wired in, the absence
    # of manual heel_height_mm/toe_spring_mm no longer means "no pose" -- it
    # means "measure the last's own geometry automatically" (this synthetic
    # box last has a flat sole, so the measured heel_height/toe_spring are
    # both 0 and the deformation is a no-op, but it's still the automatic
    # method that ran, not a manual override or a skipped pose).
    foot = _dense_box(width=90, length=270, height=60)
    cavity = _dense_box(width=95, length=282, height=65)
    result = compare_hybrid(foot, "left", cavity, "left", heel_height_mm=None, toe_spring_mm=None)
    assert result["pose_confidence"] is not None
    assert result["pose_details"]["method"] == "local_frames_v1"
    assert result["pose_details"]["heel_height_mm"] == pytest.approx(0.0, abs=0.5)


def test_forefoot_taper_too_fast_detected():
    sections = [
        {"fraction": 0.67, "width_ease_mm": -2.0},
        {"fraction": 0.75, "width_ease_mm": -7.0},  # drop of -5, exceeds -4 threshold
        {"fraction": 0.80, "width_ease_mm": -8.0},
    ]
    assert _forefoot_taper_too_fast(sections) is True


def test_forefoot_taper_not_triggered_for_gentle_taper():
    sections = [
        {"fraction": 0.67, "width_ease_mm": -2.0},
        {"fraction": 0.75, "width_ease_mm": -3.0},
        {"fraction": 0.80, "width_ease_mm": -3.5},
    ]
    assert _forefoot_taper_too_fast(sections) is False


def test_forefoot_taper_ignores_not_evaluable_sections():
    sections = [
        {"fraction": 0.67, "not_evaluable": True},
        {"fraction": 0.75, "width_ease_mm": -7.0},
        {"fraction": 0.80, "width_ease_mm": -8.0},
    ]
    assert _forefoot_taper_too_fast(sections) is False  # only one gap left (-1), under threshold


def test_critical_sections_detects_misallocated_volume():
    # foot 90x60, cavity narrower (82) but taller enough that area stays ~equal:
    # 82 * 65.85 ~= 90 * 60 -- classic "volume present, wrong shape" case.
    foot = _dense_box(width=90, length=270, height=60)
    cavity = _dense_box(width=82, length=270, height=65.85)
    sections = _critical_sections(foot, cavity)
    patterns = {s["fraction"]: s.get("pattern") for s in sections}
    assert any(p == MISALLOCATED_VOLUME for p in patterns.values())
    # sanity: the triggering section really is width-tight + dorsal-loose + area~equal
    flagged = next(s for s in sections if s.get("pattern") == MISALLOCATED_VOLUME)
    assert flagged["width_ease_mm"] < 0
    assert flagged["dorsal_top_ease_mm"] > 0
    assert abs(flagged["area_ease_mm2"]) < 150.0


def test_compare_hybrid_end_to_end_includes_critical_sections():
    foot = _dense_box(width=90, length=270, height=60)
    cavity = _dense_box(width=95, length=282, height=65)
    result = compare_hybrid(foot, "left", cavity, "left")
    assert len(result["critical_sections"]) == 6
    fractions = [s["fraction"] for s in result["critical_sections"]]
    assert fractions == [0.45, 0.50, 0.55, 0.67, 0.75, 0.80]


def test_combine_bilateral_picks_worse_side_as_limiting():
    left = _risks(tightness=0.2, looseness=0.0)
    right = _risks(tightness=0.7, looseness=0.1)
    result = combine_bilateral(left, right)
    assert result["limiting_side"] == "right"
    assert RIGHT_FOOT_DOMINANT in result["patterns"]


def test_combine_bilateral_left_dominant():
    left = _risks(tightness=0.6, looseness=0.0)
    right = _risks(tightness=0.1, looseness=0.0)
    result = combine_bilateral(left, right)
    assert result["limiting_side"] == "left"
    assert LEFT_FOOT_DOMINANT in result["patterns"]


def test_combine_bilateral_flags_last_mismatch_when_both_sides_bad():
    left = _risks(tightness=0.5, looseness=0.0)
    right = _risks(tightness=0.6, looseness=0.0)
    result = combine_bilateral(left, right)
    assert BILATERAL_LAST_MISMATCH in result["patterns"]


def test_combine_bilateral_no_mismatch_flag_when_only_one_side_bad():
    left = _risks(tightness=0.05, looseness=0.0)
    right = _risks(tightness=0.6, looseness=0.0)
    result = combine_bilateral(left, right)
    assert BILATERAL_LAST_MISMATCH not in result["patterns"]


def test_combine_bilateral_none_when_a_side_missing():
    assert combine_bilateral(_risks(0.5), None) is None
    assert combine_bilateral(None, _risks(0.5)) is None


def test_combine_bilateral_none_when_a_side_errored():
    assert combine_bilateral({"error": "boom"}, _risks(0.5)) is None
