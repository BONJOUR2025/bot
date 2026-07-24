"""Per-vertex "ease" heatmap for the foot surface in the interactive 3D
viewer -- turns the same signed-distance signal `last_fit_hybrid_service.
compare_hybrid` already buckets into 5 discrete zones into a smooth,
continuous per-vertex color gradient instead (closer to a real thermal/
pressure-map render than a handful of flat-colored patches).

Why nearest-sample-point propagation rather than an exact signed-distance
query at every vertex: `mesh3d_service.py`'s own module docstring already
establishes why a full-resolution per-vertex query is too expensive on
these meshes (~55k points against a ~110k-face mesh attempted a 7GB
allocation and took 80+ seconds) -- that's exactly the computation a naive
per-vertex heatmap would need. Reusing the existing bounded sample (~2000
points, the same sample `bidirectional_surface_distance` already computes
for compare_hybrid's own zone aggregates) and propagating each vertex's
value from its nearest sampled point via a KD-tree (scipy, already a
dependency) keeps this cheap. The nearest-sample assignment alone looks
blocky (Voronoi-cell-like), so a few passes of sparse-matrix neighbor
averaging (using the mesh's own edge connectivity, vectorized -- a plain
per-vertex Python loop over ~100k vertices would be the same class of
mistake already fixed elsewhere this session) smooth it into a continuous
gradient.
"""
from __future__ import annotations

import numpy as np
import trimesh
from scipy import sparse
from scipy.spatial import cKDTree

DEFAULT_EASE_CLAMP_MM = 6.0
_SMOOTH_PASSES = 3

# Matches mesh_visualization_service.COLORS["too_tight"] / ["too_loose"];
# the neutral midpoint is a pale "glass" tint distinct from both, rather
# than pure white, so an untouched-fit area still reads as part of the
# same material family as the tight/loose ends of the ramp.
TIGHT_RGB = (255, 0, 0)
NEUTRAL_RGB = (191, 227, 245)
LOOSE_RGB = (30, 144, 255)


def _neighbor_averaging_matrix(mesh: trimesh.Trimesh) -> sparse.csr_matrix:
    """Row-normalized (vertex + its direct neighbors) averaging matrix, built
    once from the mesh's own unique edges -- a single sparse matrix-vector
    product per smoothing pass, no per-vertex Python loop."""
    n = len(mesh.vertices)
    edges = mesh.edges_unique
    self_idx = np.arange(n)
    rows = np.concatenate([edges[:, 0], edges[:, 1], self_idx])
    cols = np.concatenate([edges[:, 1], edges[:, 0], self_idx])
    data = np.ones(len(rows), dtype=np.float64)
    adjacency = sparse.coo_matrix((data, (rows, cols)), shape=(n, n)).tocsr()
    row_sums = np.asarray(adjacency.sum(axis=1)).ravel()
    row_sums[row_sums == 0] = 1.0
    return adjacency.multiply(1.0 / row_sums[:, None]).tocsr()


def vertex_ease_values(
    mesh: trimesh.Trimesh, sample_points: np.ndarray, sample_distances: np.ndarray,
    smooth_passes: int = _SMOOTH_PASSES,
) -> np.ndarray:
    """One ease value (mm, positive=room/loose, negative=conflict/tight --
    this domain's established sign convention, see mesh3d_service.py) per
    vertex of `mesh`, propagated from the nearest sampled point and
    smoothed across the mesh's own edge connectivity."""
    finite = np.isfinite(sample_distances)
    if not finite.any() or len(mesh.vertices) == 0:
        return np.zeros(len(mesh.vertices))
    tree = cKDTree(sample_points[finite])
    _dist, nearest_idx = tree.query(mesh.vertices)
    values = sample_distances[finite][nearest_idx].astype(np.float64)

    if smooth_passes > 0 and len(mesh.edges_unique) > 0:
        smoother = _neighbor_averaging_matrix(mesh)
        for _ in range(smooth_passes):
            values = smoother @ values
    return values


def ease_to_vertex_colors(ease_values: np.ndarray, clamp_mm: float = DEFAULT_EASE_CLAMP_MM) -> np.ndarray:
    """Diverging red (tight) -> pale glass (neutral) -> blue (loose) ramp,
    clamped to +/-clamp_mm -- returns (N, 4) uint8 RGBA suitable for
    trimesh's `ColorVisuals(vertex_colors=...)`."""
    t = np.clip(ease_values / clamp_mm, -1.0, 1.0)
    tight = np.array(TIGHT_RGB, dtype=np.float64)
    neutral = np.array(NEUTRAL_RGB, dtype=np.float64)
    loose = np.array(LOOSE_RGB, dtype=np.float64)

    colors = np.empty((len(t), 3), dtype=np.float64)
    tight_mask = t < 0
    colors[tight_mask] = neutral + (tight - neutral) * (-t[tight_mask])[:, None]
    colors[~tight_mask] = neutral + (loose - neutral) * (t[~tight_mask])[:, None]

    rgba = np.empty((len(t), 4), dtype=np.uint8)
    rgba[:, :3] = np.clip(colors, 0, 255).astype(np.uint8)
    rgba[:, 3] = 255
    return rgba
