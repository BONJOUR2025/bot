"""Interactive 3D visualization payload for the admin panel's foot/last
comparison — the mesh-based counterpart to the flat matplotlib PNG overlays
`scm_parser_service.render_foot_views` / `last_fit_service._render_overlays`
already produce for slice_v1. Requested alongside `hybrid_v2` (via
`include_geometry=true` on `/lasts/match`), never computed by default —
geometry payloads are heavy and most comparisons don't need them.

Deliberately not the naive "always highlight 3 fixed length bands" approach
a first-pass spec for this describes: this instead reads the *actual*
patterns `last_fit_hybrid_service.compare_hybrid` already found (its
`patterns` list and `critical_sections`) and only builds a problem patch for
a zone/section that the algorithm itself flagged — the scene shows exactly
what the analysis concluded, not a fixed template regardless of the result.

Meshes are re-posed and re-registered here rather than reusing
`compare_hybrid`'s internal state (it doesn't expose the aligned meshes,
only computed numbers) — `apply_pose`/`register_foot_to_cavity` are
deterministic given the same inputs, so this reproduces the exact same
alignment the analysis used, at the cost of repeating that one step
(a few seconds) rather than the whole distance computation.

Serialization: GLB (binary glTF), base64-encoded inline in the JSON
response — same "data URI" pattern already used for PNG overlays elsewhere
in this codebase (scm_parser_service.py, last_fit_service.py), so no
separate static-file round trip is needed. trimesh exports GLB without any
extra dependency beyond what's already installed.

Known limitation, stated rather than silently skipped: meshes are sent at
full scan resolution (~110k faces on this scanner's real scans) — mesh
decimation for a lighter "display" copy needs the `fast_simplification`
package, which isn't installed. Fine for an internal admin tool over a
normal connection; the first thing to add if payload size or frontend
frame rate becomes a real problem.
"""
from __future__ import annotations

import base64
import io

import numpy as np
import trimesh

from app.services.last_fit_hybrid_service import (
    BALL_TIGHT_INSTEP_LOOSE,
    FOREFOOT_TAPER_TOO_FAST,
    GENERAL_OVERSIZE,
    HEEL_VOID_MIDFOOT_TIGHT,
    MEDIAL_CONFLICT_DORSAL_VOID,
    MISALLOCATED_VOLUME,
    NARROW_HIGH,
    WIDE_LOW,
    ZONES,
)
from app.services.last_pose_service import apply_pose
from app.services.last_registration_service import register_foot_to_cavity

# Explicit, documented palette (the source spec insists on this being config,
# not hardcoded scattered literals — it still lives in one place, just here).
COLORS = {
    "last_surface": "#C0C0C0",   # lightgray, per the spec's own suggested scheme
    "foot_surface": "#87CEFA",   # lightskyblue
    "too_tight": "#FF0000",       # conflict / meaningful width or height deficit
    "too_loose": "#1E90FF",       # excess room
    "misallocated_volume": "#9370DB",   # volume present, wrong shape (purple)
    "forefoot_taper_too_fast": "#8A2BE2",  # toe narrows faster than the foot (violet)
    "default_patch": "#FFA500",  # fallback (orange) — should not normally trigger
}

_LOOSE_PATTERNS = {WIDE_LOW, GENERAL_OVERSIZE, HEEL_VOID_MIDFOOT_TIGHT, BALL_TIGHT_INSTEP_LOOSE}
_TIGHT_PATTERNS = {NARROW_HIGH, MEDIAL_CONFLICT_DORSAL_VOID}

# A section-driven patch (MISALLOCATED_VOLUME / FOREFOOT_TAPER_TOO_FAST) has
# no zone of its own (it comes from a specific length fraction, not one of
# the 5 named zones) -- a narrow band around that fraction stands in for it.
_SECTION_PATCH_HALF_WIDTH_FRACTION = 0.025


def _pattern_color(pattern: str) -> str:
    if pattern == MISALLOCATED_VOLUME:
        return COLORS["misallocated_volume"]
    if pattern == FOREFOOT_TAPER_TOO_FAST:
        return COLORS["forefoot_taper_too_fast"]
    if pattern in _TIGHT_PATTERNS:
        return COLORS["too_tight"]
    if pattern in _LOOSE_PATTERNS:
        return COLORS["too_loose"]
    return COLORS["default_patch"]


def _mesh_to_glb_base64(mesh: trimesh.Trimesh) -> str:
    buf = io.BytesIO()
    mesh.export(buf, file_type="glb")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _extract_band_patch(mesh: trimesh.Trimesh, lo_frac: float, hi_frac: float) -> trimesh.Trimesh | None:
    """Submesh of `mesh` covering the length fraction range [lo_frac, hi_frac)
    — a plain Y-band selection (this codebase's length axis), matching the
    "select a longitudinal band" approach every reviewed spec agrees is fine
    for highlighting *where* a problem is, as opposed to computing one (that
    already happened upstream, in compare_hybrid)."""
    y = mesh.vertices[:, 1]
    length = float(y.max())
    if length <= 0:
        return None
    face_y = mesh.vertices[mesh.faces, 1].mean(axis=1)
    frac = face_y / length
    mask = (frac >= lo_frac) & (frac < hi_frac)
    face_indices = np.where(mask)[0]
    if len(face_indices) == 0:
        return None
    return mesh.submesh([face_indices], append=True)


def _zone_range(zone_key: str) -> tuple[float, float] | None:
    for key, lo, hi, _label in ZONES:
        if key == zone_key:
            return lo, hi
    return None


def _build_patches(final_foot: trimesh.Trimesh, hybrid_result: dict) -> list[dict]:
    patches: list[dict] = []

    for entry in hybrid_result.get("patterns", []):
        zone_key = entry.get("zone")
        pattern = entry["pattern"]
        if zone_key is None:
            continue  # cross-zone / bilateral patterns have no single band to draw
        zone_range = _zone_range(zone_key)
        if zone_range is None:
            continue
        lo, hi = zone_range
        patch_mesh = _extract_band_patch(final_foot, lo, hi)
        if patch_mesh is None:
            continue
        zone_label = hybrid_result["zones"].get(zone_key, {}).get("label", zone_key)
        patches.append({
            "zone": zone_key,
            "pattern": pattern,
            "color": _pattern_color(pattern),
            "label": f"{int(lo*100)}-{int(hi*100)}% {zone_label}",
            "mesh_glb_base64": _mesh_to_glb_base64(patch_mesh),
        })

    for section in hybrid_result.get("critical_sections", []):
        pattern = section.get("pattern")
        if pattern is None:
            continue
        frac = section["fraction"]
        lo = max(0.0, frac - _SECTION_PATCH_HALF_WIDTH_FRACTION)
        hi = min(1.0, frac + _SECTION_PATCH_HALF_WIDTH_FRACTION)
        patch_mesh = _extract_band_patch(final_foot, lo, hi)
        if patch_mesh is None:
            continue
        patches.append({
            "zone": None,
            "fraction": frac,
            "pattern": pattern,
            "color": _pattern_color(pattern),
            "label": f"≈{int(frac*100)}%",
            "mesh_glb_base64": _mesh_to_glb_base64(patch_mesh),
        })

    return patches


def _labels_for_patches(patches: list[dict], final_foot: trimesh.Trimesh) -> list[dict]:
    labels = []
    y_all = final_foot.vertices[:, 1]
    length = float(y_all.max()) if len(y_all) else 0.0
    for patch in patches:
        frac = patch.get("fraction")
        if frac is None:
            zone_range = _zone_range(patch["zone"])
            frac = sum(zone_range) / 2 if zone_range else 0.5
        y = frac * length
        # Rough label anchor: widest point of the foot at that length, lifted
        # a bit above the surface so it doesn't sit inside the mesh.
        band = np.abs(y_all - y) < max(length * 0.02, 2.0)
        x = float(final_foot.vertices[band, 0].max()) if band.any() else 0.0
        z = float(final_foot.vertices[band, 2].max()) if band.any() else 0.0
        labels.append({"text": patch["label"], "position": [x, float(y), z + 10.0], "color": patch["color"]})
    return labels


def build_visualization_payload(
    foot_mesh: trimesh.Trimesh, foot_side: str | None,
    last_mesh: trimesh.Trimesh, last_side: str | None,
    hybrid_result: dict,
    heel_height_mm: float | None = None, toe_spring_mm: float | None = None,
) -> dict:
    """Build the geometry + problem-patch payload for the interactive viewer.
    `hybrid_result` is the dict `last_fit_hybrid_service.compare_hybrid`
    already produced for this same foot/last pair — reused for which
    zones/sections to highlight rather than recomputed."""
    posed_foot, _pose_confidence = apply_pose(foot_mesh, heel_height_mm, toe_spring_mm)
    registration, foot_aligned, cavity_aligned = register_foot_to_cavity(
        posed_foot, foot_side, last_mesh, last_side,
    )
    final_foot = foot_aligned.copy()
    final_foot.vertices = registration.aligned_foot_vertices

    patches = _build_patches(final_foot, hybrid_result)
    labels = _labels_for_patches(patches, final_foot)

    return {
        "geometries": {
            "foot": {"format": "glb_base64", "data": _mesh_to_glb_base64(final_foot)},
            "last": {"format": "glb_base64", "data": _mesh_to_glb_base64(cavity_aligned)},
        },
        "layers": {
            "problem_patches": patches,
            "labels": labels,
        },
        "legend": {
            "last": COLORS["last_surface"],
            "foot": COLORS["foot_surface"],
            "too_tight": COLORS["too_tight"],
            "too_loose": COLORS["too_loose"],
            "misallocated_volume": COLORS["misallocated_volume"],
            "forefoot_taper_too_fast": COLORS["forefoot_taper_too_fast"],
        },
    }
