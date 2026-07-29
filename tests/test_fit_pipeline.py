"""Tests for fit_pipeline — the §21 pipeline and its §24.2 report shape, plus
the §28.8 report checks (every result carries analysis_mode, limitations,
confidence, and never claims pressure)."""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from app.services.fit_pipeline import (
    FIT_REQUIRES_DIFFERENT_FULLNESS,
    FIT_REQUIRES_LAST_MODIFICATION,
    analyze_fit,
)


def _blocky(width, length, height, subdivisions=4):
    mesh = trimesh.creation.box(extents=[width, length, height])
    for _ in range(subdivisions):
        mesh = mesh.subdivide()
    mesh.apply_translation([0.0, length / 2.0, height / 2.0])
    return mesh


def _tapered(back_width, front_width, length, height, subdivisions=5):
    """A last that is `back_width` wide at the heel and linearly widens (or
    narrows) to `front_width` at the toe -- unlike _blocky, tightness and
    looseness are not uniform along its length."""
    mesh = trimesh.creation.box(extents=[max(back_width, front_width), length, height])
    for _ in range(subdivisions):
        mesh = mesh.subdivide()
    v = mesh.vertices.copy()
    t = (v[:, 1] + length / 2.0) / length
    width_at = back_width + (front_width - back_width) * t
    v[:, 0] *= width_at / max(back_width, front_width)
    mesh.vertices = v
    mesh.apply_translation([0.0, length / 2.0, height / 2.0])
    return mesh


def _report(foot, last, **kw):
    return analyze_fit(foot, last, "left", "left", **kw).as_dict()


def test_report_has_the_required_envelope():
    """§28.8: mode, limitations, confidence and units-bearing sections must be
    present on every result."""
    d = _report(_blocky(90, 260, 60), _blocky(100, 285, 95))
    for key in ("engine", "fit_class", "confidence", "analysis_mode",
                "landmarks", "registration", "working_orientation",
                "cavity", "sections", "clearance", "quality", "limitations"):
        assert key in d, key
    assert d["analysis_mode"] == "STATIC_GEOMETRY"
    assert d["limitations"]
    assert 0.0 <= d["confidence"] <= 1.0


def test_pressure_is_never_claimed():
    """§25.3: the word is only allowed behind a validated mechanical model."""
    d = _report(_blocky(90, 260, 60), _blocky(100, 285, 95))
    for lim in d["limitations"]:
        assert "no pressure is computed" in lim or "pressure" not in lim.lower()
    assert any("no pressure" in lim for lim in d["limitations"])


def test_proxy_cavity_and_probabilistic_nature_are_disclosed():
    """§31.3: with two STLs the result is a geometric estimate, and the report
    has to say so rather than present a measured foot shape."""
    d = _report(_blocky(90, 260, 60), _blocky(100, 285, 95))
    assert d["cavity"]["cavity_mode"] == "LAST_PROXY"
    assert d["cavity"]["is_measured_shoe_interior"] is False
    assert any("probabilistic geometric model" in lim for lim in d["limitations"])


def test_heel_stays_pinned_through_the_whole_pipeline():
    """The §9.5 guarantee has to survive integration, not just the unit."""
    d = _report(_blocky(90, 260, 60), _blocky(105, 290, 95))
    reg = d["registration"]
    assert reg["within_tolerance"]
    assert abs(reg["posterior_heel_delta_y_mm"]) < 0.1
    assert reg["scale"] == 1.0


def test_a_uniformly_narrower_last_needs_a_different_fullness():
    """Tight everywhere, loose nowhere, and the same height as the foot, on a
    last that already passed the size/proportion gate is exactly what the
    next width grade down looks like -- not a defect that needs the last
    reshaped. Height is held equal to the foot's own on purpose: a narrower
    AND taller last is a different, worse case (see
    test_narrow_and_tall_last_needs_modification_not_fullness below)."""
    foot = _blocky(100, 260, 60)
    narrow = _blocky(70, 285, 60)
    d = _report(foot, narrow)
    assert d["fit_class"] == FIT_REQUIRES_DIFFERENT_FULLNESS
    assert d["fullness_direction"] == "wider"
    assert d["fullness_mm"] > 0


def test_a_uniformly_wider_last_needs_a_different_fullness_the_other_way():
    foot = _blocky(100, 260, 60)
    wide = _blocky(130, 285, 60)
    d = _report(foot, wide)
    assert d["fit_class"] == FIT_REQUIRES_DIFFERENT_FULLNESS
    assert d["fullness_direction"] == "narrower"


def test_mixed_tight_and_loose_still_needs_modification():
    """A last that is narrow at the heel and flares wide at the toe is not
    fixable by picking a different fullness of the same model -- squeeze and
    void at once is a shape problem, not a grading problem."""
    foot = _blocky(90, 260, 60)
    lopsided = _tapered(back_width=65, front_width=140, length=278, height=100)
    d = _report(foot, lopsided)
    assert d["fit_class"] == FIT_REQUIRES_LAST_MODIFICATION
    assert d["fullness_direction"] is None
    assert d["fullness_mm"] is None


def test_narrow_and_tall_last_needs_modification_not_fullness():
    """The real bug: a last narrower in width AND taller in height than the
    foot, uniformly along its whole length, used to read as "every zone is
    LOCAL_TIGHTNESS" (the zone label is won by the worst direction, which is
    the width squeeze) and get diagnosed as needing a wider fullness. An
    independent cross-section check on a real pair found the last was
    simultaneously 2-5mm narrower AND 6-13mm taller than the foot at every Y
    level from mid-foot to the toes -- a misallocated-volume last that a
    wider fullness of the same model would not fix, since it is already too
    tall. This is that pattern, reproduced synthetically."""
    foot = _blocky(100, 260, 60)
    narrow_and_tall = _blocky(70, 285, 95)
    d = _report(foot, narrow_and_tall)
    assert d["fit_class"] == FIT_REQUIRES_LAST_MODIFICATION
    assert d["fullness_direction"] is None
    assert d["fullness_mm"] is None


def test_pose_uncertainty_is_absent_in_static_mode():
    """§20.1: static geometry infers no pose, so that budget stays at zero."""
    d = _report(_blocky(90, 260, 60), _blocky(105, 285, 95))
    assert d["clearance"]["uncertainty"]["pose_sigma_mm"] == 0.0


def test_inputs_are_not_mutated():
    """§19.1: the raw meshes are preserved."""
    foot, last = _blocky(90, 260, 60), _blocky(105, 285, 95)
    fv, lv = foot.vertices.copy(), last.vertices.copy()
    analyze_fit(foot, last, "left", "left")
    assert np.array_equal(foot.vertices, fv)
    assert np.array_equal(last.vertices, lv)


def test_construction_overrides_reach_the_cavity():
    thick = {"insole_thickness_mm": 8.0, "lining_thickness_mm": 4.0}
    d = _report(_blocky(90, 260, 60), _blocky(105, 285, 95), construction=thick)
    assert d["cavity"]["construction"]["insole_thickness_mm"] == 8.0
    assert d["cavity"]["offsets_applied_mm"]["sole_up"] == pytest.approx(8.0)


def test_the_same_pair_analysed_twice_gives_the_same_answer():
    """The surface sample used to be unseeded, so identical inputs returned
    different reports: the same foot and last, five runs in a row, produced
    three different fit classes and flipped the ball zone between looseness
    and tightness. A report that changes on reload cannot be checked against
    a real fitting, or against itself."""
    foot, last = _blocky(95, 265, 58), _blocky(104, 285, 92)
    first = _report(foot, last)
    second = _report(foot, last)

    assert first["fit_class"] == second["fit_class"]
    assert ([z["classification"] for z in first["clearance"]["zones"]]
            == [z["classification"] for z in second["clearance"]["zones"]])
    assert ([z["signed_gap_mm"]["median"] for z in first["clearance"]["zones"]]
            == [z["signed_gap_mm"]["median"] for z in second["clearance"]["zones"]])


def test_a_last_is_not_called_good_while_a_warning_stands():
    """fit_class comes from the zone clearance alone, so a last can pass every
    zone while its length allowance sits well outside the band. Heading that
    "Колодка подходит" over a warning that it is 23mm too long leaves the
    reader to resolve the contradiction."""
    d = _report(_blocky(92, 262, 56), _blocky(100, 300, 88))   # allowance ~38mm
    ex = d["explanation"]
    warned = [f for f in ex["findings"] if f["severity"] in ("critical", "warning")]
    assert warned, "fixture should raise at least one warning"
    assert ex["headline"] != "Колодка подходит"


def test_the_heel_is_seated_against_the_cavity_not_the_last():
    """Registration pins the heel to the last, but clearance is measured
    against the cavity, whose back sits forward of it by the heel counter's
    thickness. Uncorrected, every foot hangs behind every cavity and the
    posterior heel reads as tight -- measured at a median -3.0mm on a real
    pair whose wearer reported that heel as loose."""
    thick = {"heel_counter_thickness_mm": 6.0, "insole_thickness_mm": 5.0}
    d = _report(_blocky(90, 260, 60), _blocky(104, 285, 92), construction=thick)
    zones = {z["name"]: z for z in d["clearance"]["zones"]}
    assert zones["posterior_heel"]["classification"] != "LOCAL_TIGHTNESS"
    assert any("seated inside the cavity" in lim for lim in d["limitations"])


def test_broad_slack_with_one_small_press_is_not_called_a_reshape():
    """The rule "tight somewhere and loose somewhere -> misallocated volume"
    was blind to magnitude, so a small press outranked much larger slack and
    headlined the last as needing reshaping. When one side clearly dominates
    it is the verdict; the other stays a finding."""
    foot = _blocky(90, 260, 60)
    roomy = _blocky(122, 285, 96)
    d = _report(foot, roomy)
    zones = {z["name"]: z["classification"] for z in d["clearance"]["zones"]}
    assert "LOCAL_LOOSENESS" in zones.values(), "fixture must actually be loose"
    assert d["fit_class"] != FIT_REQUIRES_LAST_MODIFICATION


def test_comparable_tightness_and_slack_still_reads_as_reshaping():
    """Dominance is the escape hatch, not a way out of the verdict: when the
    two sides are of similar size the volume really is in the wrong place."""
    foot = _blocky(90, 260, 60)
    lopsided = _tapered(back_width=64, front_width=140, length=278, height=100)
    d = _report(foot, lopsided)
    assert d["fit_class"] == FIT_REQUIRES_LAST_MODIFICATION
