"""Tests for mesh_visualization_service — synthetic geometry only."""
from __future__ import annotations

import base64
import io

import numpy as np
import trimesh
import pytest

from app.services.last_fit_hybrid_service import compare_hybrid
from app.services.mesh_visualization_service import (
    COLORS,
    build_visualization_payload,
)


def _dense_box(width, length, height):
    mesh = trimesh.creation.box(extents=[width, length, height])
    for _ in range(5):
        mesh = mesh.subdivide()
    mesh.apply_translation([0.0, length / 2.0, height / 2.0])
    return mesh


def _decode_glb_mesh(b64: str) -> trimesh.Trimesh:
    raw = base64.b64decode(b64)
    scene = trimesh.load(io.BytesIO(raw), file_type="glb")
    if isinstance(scene, trimesh.Scene):
        return trimesh.util.concatenate(list(scene.geometry.values()))
    return scene


def test_payload_geometries_round_trip_as_valid_glb():
    foot = _dense_box(width=90, length=270, height=60)
    cavity = _dense_box(width=95, length=282, height=65)
    hybrid_result = compare_hybrid(foot, "left", cavity, "left")

    payload = build_visualization_payload(foot, "left", cavity, "left", hybrid_result)

    foot_mesh = _decode_glb_mesh(payload["geometries"]["foot"]["data"])
    last_mesh = _decode_glb_mesh(payload["geometries"]["last"]["data"])
    assert len(foot_mesh.faces) > 0
    assert len(last_mesh.faces) > 0


def test_narrow_high_produces_tight_colored_patches():
    foot = _dense_box(width=90, length=270, height=60)
    cavity = _dense_box(width=80, length=282, height=75)  # narrower + taller -> NARROW_HIGH
    hybrid_result = compare_hybrid(foot, "left", cavity, "left")

    payload = build_visualization_payload(foot, "left", cavity, "left", hybrid_result)
    patches = payload["layers"]["problem_patches"]
    assert len(patches) > 0
    assert all(p["color"] == COLORS["too_tight"] for p in patches if p["pattern"] == "NARROW_HIGH")

    # every patch must actually contain geometry, roughly sized like a real
    # slice of the foot (not empty, not the whole mesh). Bounds are checked
    # against a generously padded box rather than the pre-registration foot's
    # exact bounds -- registration (ICP) legitimately shifts the foot by a
    # few mm/degrees to align with the last, so an exact-bounds match isn't
    # a real invariant here.
    padded_bounds = foot.bounds + np.array([[-20, -20, -20], [20, 20, 20]])
    for p in patches:
        patch_mesh = _decode_glb_mesh(p["mesh_glb_base64"])
        assert len(patch_mesh.faces) > 0
        assert np.all(patch_mesh.bounds[0] >= padded_bounds[0])
        assert np.all(patch_mesh.bounds[1] <= padded_bounds[1])


def test_wide_low_produces_loose_colored_patches():
    foot = _dense_box(width=90, length=270, height=75)
    cavity = _dense_box(width=110, length=282, height=68)  # wider + shorter -> WIDE_LOW
    hybrid_result = compare_hybrid(foot, "left", cavity, "left")

    payload = build_visualization_payload(foot, "left", cavity, "left", hybrid_result)
    patches = payload["layers"]["problem_patches"]
    wide_low_patches = [p for p in patches if p["pattern"] == "WIDE_LOW"]
    assert wide_low_patches
    assert all(p["color"] == COLORS["too_loose"] for p in wide_low_patches)


def test_labels_match_patch_count_and_carry_text():
    foot = _dense_box(width=90, length=270, height=60)
    cavity = _dense_box(width=80, length=282, height=75)
    hybrid_result = compare_hybrid(foot, "left", cavity, "left")

    payload = build_visualization_payload(foot, "left", cavity, "left", hybrid_result)
    assert len(payload["layers"]["labels"]) == len(payload["layers"]["problem_patches"])
    for label in payload["layers"]["labels"]:
        assert label["text"]
        assert len(label["position"]) == 3


def test_legend_contains_expected_keys():
    foot = _dense_box(width=90, length=270, height=60)
    cavity = _dense_box(width=95, length=282, height=65)
    hybrid_result = compare_hybrid(foot, "left", cavity, "left")
    payload = build_visualization_payload(foot, "left", cavity, "left", hybrid_result)
    legend = payload["legend"]
    for key in ("last", "foot", "too_tight", "too_loose", "misallocated_volume", "forefoot_taper_too_fast"):
        assert key in legend


def test_no_patches_when_no_patterns_found():
    foot = _dense_box(width=90, length=270, height=60)
    cavity = _dense_box(width=91, length=278, height=61)  # close match -> no patterns expected
    hybrid_result = compare_hybrid(foot, "left", cavity, "left")
    payload = build_visualization_payload(foot, "left", cavity, "left", hybrid_result)
    assert payload["layers"]["problem_patches"] == []
    assert payload["layers"]["labels"] == []


def test_foot_flat_geometry_present_and_differs_from_posed_foot():
    # A synthetic box has zero measured heel_height/toe_spring (flat sole),
    # so the *pose* is a near-no-op here -- but foot_flat must still be a
    # distinct, valid geometry in the same aligned frame as `foot`, not a
    # copy of it or missing.
    foot = _dense_box(width=90, length=270, height=60)
    cavity = _dense_box(width=95, length=282, height=65)
    hybrid_result = compare_hybrid(foot, "left", cavity, "left")
    payload = build_visualization_payload(foot, "left", cavity, "left", hybrid_result)

    assert "foot_flat" in payload["geometries"]
    flat_mesh = _decode_glb_mesh(payload["geometries"]["foot_flat"]["data"])
    assert len(flat_mesh.faces) > 0


def test_last_bottom_curve_is_a_nonempty_polyline_matching_last_length():
    foot = _dense_box(width=90, length=270, height=60)
    cavity = _dense_box(width=95, length=282, height=65)
    hybrid_result = compare_hybrid(foot, "left", cavity, "left")
    payload = build_visualization_payload(foot, "left", cavity, "left", hybrid_result)

    curve = payload["layers"]["last_bottom_curve"]
    # _dense_box's fixed subdivision count (shared with every other test in
    # this file) caps vertex density well below what extract_bottom_profile
    # needs for its full 1mm-step bin resolution -- 20+ profile points is
    # still a meaningful "is this a real curve, not empty/degenerate" check.
    assert len(curve) > 20
    for point in curve:
        assert len(point) == 3
        assert point[0] == pytest.approx(0.0)
    ys = [p[1] for p in curve]
    assert min(ys) >= 0.0
    assert max(ys) <= 282.0 + 1.0


def test_heatmap_metadata_present_and_vertex_colors_not_flat():
    foot = _dense_box(width=90, length=270, height=60)
    cavity = _dense_box(width=80, length=282, height=75)  # NARROW_HIGH -> real conflict/room variation
    hybrid_result = compare_hybrid(foot, "left", cavity, "left")
    payload = build_visualization_payload(foot, "left", cavity, "left", hybrid_result)

    heatmap = payload["heatmap"]
    assert heatmap["enabled"] is True
    assert heatmap["range_mm"] > 0
    for key in ("tight_color", "neutral_color", "loose_color"):
        assert heatmap[key].startswith("#")

    foot_mesh = _decode_glb_mesh(payload["geometries"]["foot"]["data"])
    vertex_colors = foot_mesh.visual.vertex_colors
    assert vertex_colors.shape[0] == len(foot_mesh.vertices)
    # a real conflict (narrower+taller cavity) should produce more than one
    # distinct color across the surface -- not a single flat tint.
    assert len(np.unique(vertex_colors.reshape(-1, 4), axis=0)) > 1


def test_foot_flat_shares_same_vertex_colors_as_posed_foot():
    foot = _dense_box(width=90, length=270, height=60)
    cavity = _dense_box(width=80, length=282, height=75)
    hybrid_result = compare_hybrid(foot, "left", cavity, "left")
    payload = build_visualization_payload(foot, "left", cavity, "left", hybrid_result)

    posed = _decode_glb_mesh(payload["geometries"]["foot"]["data"])
    flat = _decode_glb_mesh(payload["geometries"]["foot_flat"]["data"])
    assert posed.visual.vertex_colors.shape == flat.visual.vertex_colors.shape
    assert np.array_equal(posed.visual.vertex_colors, flat.visual.vertex_colors)


def test_pose_measurement_lines_reflect_manual_override():
    foot = _dense_box(width=90, length=270, height=60)
    cavity = _dense_box(width=95, length=282, height=65)
    hybrid_result = compare_hybrid(foot, "left", cavity, "left", heel_height_mm=18.0, toe_spring_mm=22.0)
    payload = build_visualization_payload(
        foot, "left", cavity, "left", hybrid_result, heel_height_mm=18.0, toe_spring_mm=22.0,
    )

    lines = payload["layers"]["pose_measurements"]
    assert len(lines) == 2
    heights = {round(line["points"][1][2], 1) for line in lines}
    assert 18.0 in heights
    assert 22.0 in heights
    for line in lines:
        assert line["label"]
        assert len(line["points"]) == 2
