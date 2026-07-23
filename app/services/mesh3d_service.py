"""Mesh quality gating + surface distance for the emerging hybrid_v2
(mesh-based) pipeline — stages 2 and 3 of the slice_v1 -> hybrid_v2 migration
(see docs/last_fit_system_overview.md and the migration plan).

Nothing here is used by slice_v1. It exists because surface distance
(stage 3), anatomical registration (stage 4) and pose (stage 5) all depend on
how trustworthy the mesh is — getting the *sign* of a distance wrong on a
broken mesh (open, self-intersecting, multiple disconnected shells) is worse
than not computing a signed distance at all. This module answers "is this
mesh good enough for X" before any of that later code runs.

On shin/ankle contamination (foot+leg scans go up to ~125mm, see
last_fit_service.py's own notes): a real reference scan
(scm_decode/.../_L.stl) was checked cross-section by cross-section along Z
before writing this module. There is no sharp area drop marking a
foot-to-shin transition to cut at — the cross-section narrows *smoothly and
monotonically* from the sole all the way to the top of the scan (cone-like,
not "foot then a roughly-cylindrical leg"). A geometric `ankle_cut_plane`
based on an area-drop threshold would therefore be guessing at a boundary
that isn't actually there in this scanner's data, not a validated cut. Rather
than invent an unvalidated threshold, this stays consistent with the
existing, already-validated approach in last_fit_service.py
(`ZONE_HEIGHT_MATTERS` / `ZONE_GIRTH_MATTERS`): exclude
contaminated-by-construction zones from confidence-bearing computations
instead of trying to surgically cut the mesh. Later stages (registration
masks, stage 4; conflict clustering, stage 6) should mask by the same
per-zone length fraction rather than introduce a new geometric cut.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh
import trimesh.repair as trimesh_repair

# A hole with this little boundary (mm) is a technical scanning gap, not
# missing anatomy — safe to auto-repair. Anything longer is left alone: the
# migration plan is explicit that large holes must never be silently capped,
# since that fabricates surface where there is no scan data.
MAX_AUTO_REPAIR_BOUNDARY_MM = 30.0


@dataclass
class MeshQualityReport:
    n_vertices: int
    n_faces: int
    watertight: bool
    winding_consistent: bool
    is_volume: bool  # trimesh's own composite: watertight + consistently wound +
                      # normals consistent with winding — the practical
                      # "manifold enough to trust as a solid" signal; a bespoke
                      # manifold check would need CGAL-grade tooling to do better.
    degenerate_faces: int
    duplicate_faces: int
    connected_components: int
    open_boundary_mm: float
    self_intersections: str = "not_checked"  # a robust check needs python-fcl/CGAL,
                                              # not in the approved stack (trimesh +
                                              # scipy + networkx) — reported honestly
                                              # as unknown, not as "passed".
    valid_for_closest_point: bool = True
    valid_for_unsigned_distance: bool = True
    valid_for_signed_distance: bool = False
    valid_for_boolean_volume: bool = False

    def as_dict(self) -> dict:
        return {
            "n_vertices": self.n_vertices,
            "n_faces": self.n_faces,
            "watertight": self.watertight,
            "winding_consistent": self.winding_consistent,
            "is_volume": self.is_volume,
            "degenerate_faces": self.degenerate_faces,
            "duplicate_faces": self.duplicate_faces,
            "connected_components": self.connected_components,
            "open_boundary_mm": self.open_boundary_mm,
            "self_intersections": self.self_intersections,
            "valid_for_closest_point": self.valid_for_closest_point,
            "valid_for_unsigned_distance": self.valid_for_unsigned_distance,
            "valid_for_signed_distance": self.valid_for_signed_distance,
            "valid_for_boolean_volume": self.valid_for_boolean_volume,
        }


def _boundary_length_mm(mesh: trimesh.Trimesh) -> float:
    """Total length of open-edge loops. 0.0 for a closed (watertight) mesh."""
    outline = mesh.outline(process=False)
    if outline is None or len(outline.entities) == 0:
        return 0.0
    return float(sum(e.length(outline.vertices) for e in outline.entities))


def _duplicate_face_count(mesh: trimesh.Trimesh) -> int:
    sorted_faces = np.sort(mesh.faces, axis=1)
    n_unique = len(np.unique(sorted_faces, axis=0))
    return int(len(mesh.faces) - n_unique)


def mesh_quality_report(mesh: trimesh.Trimesh) -> MeshQualityReport:
    """Compute the quality/fitness signals gating later stages of hybrid_v2."""
    n_faces = len(mesh.faces)
    degenerate = int((~mesh.nondegenerate_faces()).sum()) if n_faces else 0
    duplicate = _duplicate_face_count(mesh) if n_faces else 0
    components = len(mesh.split(only_watertight=False)) if n_faces else 0
    boundary_mm = _boundary_length_mm(mesh) if n_faces else 0.0
    watertight = bool(mesh.is_watertight)
    winding = bool(mesh.is_winding_consistent)
    is_volume = bool(mesh.is_volume)

    report = MeshQualityReport(
        n_vertices=len(mesh.vertices),
        n_faces=n_faces,
        watertight=watertight,
        winding_consistent=winding,
        is_volume=is_volume,
        degenerate_faces=degenerate,
        duplicate_faces=duplicate,
        connected_components=components,
        open_boundary_mm=round(boundary_mm, 2),
    )
    report.valid_for_closest_point = n_faces > 0
    report.valid_for_unsigned_distance = n_faces > 0
    # Signed distance needs a genuine closed volume with one shell — trimesh's
    # winding-number method degrades silently on anything less, which is
    # exactly the "trusting the sign of an open mesh" the migration plan
    # warns against.
    report.valid_for_signed_distance = is_volume and components == 1
    report.valid_for_boolean_volume = (
        is_volume and components == 1 and degenerate == 0 and duplicate == 0
    )
    return report


def repair_small_holes(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, bool]:
    """Return (mesh_to_use, was_repaired). The input mesh is never mutated —
    original and repaired copies are kept separate, per the migration plan
    ("исходная и repaired-сетка должны сохраняться раздельно"). Holes longer
    than MAX_AUTO_REPAIR_BOUNDARY_MM are left alone rather than auto-capped."""
    boundary_mm = _boundary_length_mm(mesh)
    if boundary_mm == 0.0 or boundary_mm > MAX_AUTO_REPAIR_BOUNDARY_MM:
        return mesh, False
    repaired = mesh.copy()
    trimesh_repair.fill_holes(repaired)
    return repaired, True


# -- surface distance (stage 3) ---------------------------------------------
#
# The whole point of this stage, per the migration plan's own critique (§4):
# distance to the nearest *surface point* is not the same as distance to the
# nearest *vertex* — a query point can sit close to the middle of a triangle
# yet far from all three of its corners, and vertex-only distance
# systematically overstates the gap in that case. `trimesh.proximity` already
# does the real point-to-triangle nearest-point query (needs `rtree` for the
# spatial index — installed alongside trimesh/scipy/networkx for this).
#
# Sign convention: trimesh.proximity.signed_distance(mesh, points) is
# positive when `points` are *inside* `mesh`, negative when outside — checked
# directly against a real reference mesh (center of mass -> positive, a point
# far outside the bounding box -> negative). That is already exactly the
# migration plan's own convention (§10): calling
# `signed_distance(cavity_mesh, foot_points)` gives >0 where the foot has
# room inside the last's volume, <0 where the foot pokes out of it. No sign
# flip needed anywhere in this module.
#
# Performance note (measured against a real reference scan pair, 55k
# vertices / 110k faces each): trimesh's signed_distance is cheap for query
# points whose nearest surface point falls inside its triangle (a local
# normal-projection sign test), but falls back to ray-casting containment
# tests for points that don't — and that fallback blew up to a 7GB
# allocation and 80+ seconds querying every one of 55k vertices at once.
# Rather than query every vertex, this samples a bounded number of points
# from the surface (`trimesh.sample.sample_surface`, itself area-weighted —
# uniform sampling density directly represents area) — ~5s for 3000 points
# in that same test. That trades per-vertex heatmap resolution for a
# tractable per-request cost, appropriate for stage 3 ("shadow" — computed
# for inspection, not yet decision-driving); stage 6's connected-conflict-zone
# work, which does need per-face resolution, should query the full mesh but
# only where stage 3's sampled aggregates already flag a zone as worth it.

DEFAULT_MAX_SAMPLE_POINTS = 2000


def _sample_surface_points(mesh: trimesh.Trimesh, max_points: int) -> tuple[np.ndarray, np.ndarray]:
    """Returns (points, normals) — the face normal at each sampled point,
    used by stage 6 to classify a point as medial/lateral/dorsal/plantar-
    *facing* rather than just by raw position (a box's flat top face has
    plenty of points with x>=0, but they aren't "medial surface" in any
    meaningful sense — their normal points in +Z, not +X)."""
    if len(mesh.faces) == 0:
        return mesh.vertices, np.zeros_like(mesh.vertices)
    n = min(max_points, len(mesh.vertices))
    points, face_index = trimesh.sample.sample_surface(mesh, n)
    normals = mesh.face_normals[face_index]
    return points, normals


def surface_distance(source_points: np.ndarray, target_mesh: trimesh.Trimesh,
                      target_quality: MeshQualityReport) -> dict:
    """Distance from each of `source_points` to `target_mesh`'s surface —
    signed when `target_quality` allows it (closed, single-shell volume),
    unsigned closest-point distance otherwise (never fabricates a sign on a
    mesh that isn't trustworthy enough for one, per stage 2's gating)."""
    if target_quality.valid_for_signed_distance:
        distances = trimesh.proximity.signed_distance(target_mesh, source_points)
        signed = True
    else:
        _, distances, _ = trimesh.proximity.closest_point(target_mesh, source_points)
        signed = False
    # "points" carried alongside distances -- stage 6 buckets both by
    # position (zone/direction), so it needs the two arrays paired up.
    return {"points": source_points, "distances": distances, "signed": signed}


def bidirectional_surface_distance(
    foot_mesh: trimesh.Trimesh, foot_quality: MeshQualityReport,
    cavity_mesh: trimesh.Trimesh, cavity_quality: MeshQualityReport,
    max_sample_points: int = DEFAULT_MAX_SAMPLE_POINTS,
) -> dict:
    """Both directions, as the migration plan requires (§10) — one-sided
    distance alone misses half the picture: foot->cavity shows conflict/
    contact/room right at the foot's own surface, cavity->foot shows where
    the cavity has empty volume the foot never gets near."""
    foot_points, foot_normals = _sample_surface_points(foot_mesh, max_sample_points)
    cavity_points, cavity_normals = _sample_surface_points(cavity_mesh, max_sample_points)
    foot_to_cavity = surface_distance(foot_points, cavity_mesh, cavity_quality)
    foot_to_cavity["normals"] = foot_normals
    cavity_to_foot = surface_distance(cavity_points, foot_mesh, foot_quality)
    cavity_to_foot["normals"] = cavity_normals
    return {
        "foot_to_cavity": foot_to_cavity,
        "cavity_to_foot": cavity_to_foot,
        "foot_surface_area_mm2": float(foot_mesh.area),
        "cavity_surface_area_mm2": float(cavity_mesh.area),
    }


def distance_aggregates(distances: np.ndarray, total_area_mm2: float | None = None) -> dict:
    """Summary stats for one direction's distance array — min/percentiles/max
    per the migration plan (§10), plus negative/contact area estimated as
    (fraction of sampled points meeting the condition) x total surface area
    — valid because the points come from area-weighted surface sampling, not
    a plain vertex list."""
    finite = distances[np.isfinite(distances)]
    if finite.size == 0:
        return {
            "min": None, "p01": None, "p05": None, "p10": None,
            "median": None, "p90": None, "p95": None, "max": None,
            "negative_area_mm2": None, "contact_area_mm2": None,
        }
    pct = lambda p: round(float(np.percentile(finite, p)), 2)

    negative_area = contact_area = None
    if total_area_mm2 is not None:
        negative_area = round(float((finite < 0).mean()) * total_area_mm2, 1)
        # "contact" = within a small band of the surface, not just d==0 exactly
        contact_area = round(float((np.abs(finite) <= 0.5).mean()) * total_area_mm2, 1)

    return {
        "min": round(float(finite.min()), 2),
        "p01": pct(1), "p05": pct(5), "p10": pct(10),
        "median": round(float(np.median(finite)), 2),
        "p90": pct(90), "p95": pct(95),
        "max": round(float(finite.max()), 2),
        "negative_area_mm2": negative_area,
        "contact_area_mm2": contact_area,
    }
