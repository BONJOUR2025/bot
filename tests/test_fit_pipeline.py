"""Tests for fit_pipeline — the §21 pipeline and its §24.2 report shape, plus
the §28.8 report checks (every result carries analysis_mode, limitations,
confidence, and never claims pressure)."""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from app.services.fit_pipeline import (
    FIT_REQUIRES_LAST_MODIFICATION,
    analyze_fit,
)


def _blocky(width, length, height, subdivisions=4):
    mesh = trimesh.creation.box(extents=[width, length, height])
    for _ in range(subdivisions):
        mesh = mesh.subdivide()
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


def test_a_much_narrower_last_needs_modification():
    foot = _blocky(100, 260, 60)
    narrow = _blocky(70, 285, 95)
    d = _report(foot, narrow)
    assert d["fit_class"] == FIT_REQUIRES_LAST_MODIFICATION


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
