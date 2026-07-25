"""Tests for shoe_cavity — §7.2/§7.3. On the real Prada 43 last the proxy
cavity comes out 11.9% smaller by volume than the last itself, which is the
margin that comparing straight against the last was silently giving away."""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from app.services.shoe_cavity import DEFAULT_CONSTRUCTION, build_cavity


def _last_like(width=100.0, length=280.0, height=90.0, subdivisions=4):
    mesh = trimesh.creation.box(extents=[width, length, height])
    for _ in range(subdivisions):
        mesh = mesh.subdivide()
    mesh.apply_translation([0.0, length / 2.0, height / 2.0])
    return mesh


def test_cavity_is_strictly_smaller_than_the_last():
    """§7.3: the foot meets the shoe interior, which every construction layer
    makes smaller than the last it was built on."""
    last = _last_like()
    cavity = build_cavity(last)
    assert cavity.mesh.volume < last.volume
    assert cavity.mesh.extents[0] < last.extents[0]


def test_cavity_is_labelled_as_a_proxy_not_a_measurement():
    """§7.2: the mode has to travel with the geometry so no report can present
    an estimate as a measured shoe interior."""
    cavity = build_cavity(_last_like())
    d = cavity.as_dict()
    assert d["cavity_mode"] == "LAST_PROXY"
    assert d["is_measured_shoe_interior"] is False
    assert "lacing_closure" in d["unmodelled_regions"]


def test_input_last_is_not_mutated():
    """§19.1: each stage returns new objects and leaves its input alone."""
    last = _last_like()
    before = last.vertices.copy()
    build_cavity(last)
    assert np.array_equal(last.vertices, before)


def test_thicker_construction_gives_a_smaller_cavity():
    last = _last_like()
    thin = build_cavity(last, {"lining_thickness_mm": 0.5, "insole_thickness_mm": 1.0})
    thick = build_cavity(last, {"lining_thickness_mm": 3.0, "insole_thickness_mm": 6.0})
    assert thick.mesh.volume < thin.mesh.volume


def test_offsets_report_matches_the_requested_construction():
    cfg = {"insole_thickness_mm": 3.0, "lining_thickness_mm": 1.5,
           "heel_counter_thickness_mm": 2.0, "toe_puff_thickness_mm": 1.0}
    cavity = build_cavity(_last_like(), cfg)
    applied = cavity.offsets_applied_mm
    assert applied["sole_up"] == pytest.approx(3.0)
    assert applied["heel_inward"] == pytest.approx(3.5)   # lining + counter
    assert applied["toe_inward"] == pytest.approx(2.5)    # lining + puff
    assert applied["vamp_inward"] == pytest.approx(1.5)


def test_defaults_are_reported_so_they_can_be_challenged():
    """The allowances are uncalibrated starting values (§29), so they must be
    visible in the output rather than buried in the code."""
    cavity = build_cavity(_last_like())
    assert cavity.as_dict()["construction"] == DEFAULT_CONSTRUCTION
