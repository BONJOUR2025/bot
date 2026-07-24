"""Sanity-check a piecewise foot deformation before trusting its output --
stage 3's safety net (heel_toe_measurement_foot_deformation_visualization_
spec.md §17.1-17.4). `deform_foot_to_last_pose` moves vertices but never
touches topology, so `deformed_mesh` shares `original_mesh`'s faces/edges;
every metric here compares the same edge/face at two vertex positions
rather than doing any correspondence search.

Self-intersection detection (a full BVH intersection test) is deliberately
not implemented here, matching this session's established pattern in
mesh3d_service.py of reporting `"not_checked"` rather than silently
skipping or adding a heavy dependency for a single check.
"""
from __future__ import annotations

import numpy as np
import trimesh


def validate_deformation(original_mesh: trimesh.Trimesh, deformed_mesh: trimesh.Trimesh) -> dict:
    orig_v = original_mesh.vertices
    def_v = deformed_mesh.vertices

    edges = original_mesh.edges_unique
    orig_lengths = np.linalg.norm(orig_v[edges[:, 0]] - orig_v[edges[:, 1]], axis=1)
    def_lengths = np.linalg.norm(def_v[edges[:, 0]] - def_v[edges[:, 1]], axis=1)
    safe_orig = np.where(orig_lengths > 1e-9, orig_lengths, np.nan)
    strain = np.abs(def_lengths - orig_lengths) / safe_orig
    strain = strain[~np.isnan(strain)]
    mean_edge_strain = float(np.mean(strain)) if strain.size else 0.0
    p95_edge_strain = float(np.percentile(strain, 95)) if strain.size else 0.0

    area_ratio = float(deformed_mesh.area / original_mesh.area) if original_mesh.area > 1e-9 else None

    volume_ratio = None
    if original_mesh.is_watertight and deformed_mesh.is_watertight and abs(original_mesh.volume) > 1e-9:
        volume_ratio = float(deformed_mesh.volume / original_mesh.volume)

    orig_normals = original_mesh.face_normals
    def_normals = deformed_mesh.face_normals
    dots = np.einsum("ij,ij->i", orig_normals, def_normals)
    valid = ~np.isnan(dots)
    flipped_face_fraction = float(np.mean(dots[valid] < 0.0)) if valid.any() else 0.0

    return {
        "mean_edge_strain": round(mean_edge_strain, 4),
        "p95_edge_strain": round(p95_edge_strain, 4),
        "area_ratio": round(area_ratio, 4) if area_ratio is not None else None,
        "volume_ratio": round(volume_ratio, 4) if volume_ratio is not None else None,
        "flipped_face_fraction": round(flipped_face_fraction, 4),
        "self_intersections": "not_checked",
    }
