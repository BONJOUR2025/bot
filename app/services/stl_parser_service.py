"""Parser for .stl foot/last scans — the scanner's alternate export format
alongside .scm (see scm_parser_service's module docstring for that format).

Unlike .scm, a .stl file is a real triangulated mesh (no undocumented byte
scanning needed) and — confirmed against a real reference export — uses the
exact same coordinate convention as .scm: Y is length from the heel (y=0 at
the heel-back plane), Z is height from the sole (z=0 at the ground plane,
including part of the shin like .scm scans do), X is medial-lateral width.
That means every downstream measurement (profile, girths, rendering) is
reused unchanged from scm_parser_service — only vertex extraction differs.

A .stl export is also structured differently from .scm: one file holds one
side only (a left/right pair comes as two separate files), not both feet in
one container. So this module returns a single measurement dict (one block),
and it's the caller's job to attach which side ("left"/"right") the file
represents — there's no side hint in the file itself to read.

Mesh loading uses `trimesh` (binary + ASCII STL, degenerate-face removal,
vertex welding with a real index remap — not a bare `np.unique` on
coordinates, which would desync faces from vertices; see
`docs/last_fit_system_overview.md`'s note on this and the slice_v1 ->
hybrid_v2 migration plan, stage 1). `load_stl_mesh()` is the entry point for
the emerging mesh-based (hybrid_v2) pipeline — it keeps faces and normals.
`parse_stl()`, used by the existing slice_v1 pipeline, still reduces the mesh
to a bare point cloud on purpose: slice_v1's measurements (extract_profile,
girths) only ever needed vertex positions, never face connectivity, and
freezing that behavior is the whole point of stage 0 of the migration — this
function's output shape and numbers must not change.
"""
from __future__ import annotations

import io

import trimesh

from app.services.scm_parser_service import (
    FootBlock,
    _ball_line_mm,
    _instep_girth,
    _strip_outlier_points,
    extract_profile,
    render_foot_views,
)

# Same anatomical bounds used by scm_parser_service.find_foot_blocks to
# reject non-foot geometry — kept in sync deliberately rather than imported,
# since importing private module-level constants across files is no clearer
# than restating four numbers.
_MIN_LENGTH_MM, _MAX_LENGTH_MM = 100.0, 400.0
_MIN_WIDTH_MM, _MAX_WIDTH_MM = 30.0, 200.0
_MIN_HEIGHT_MM, _MAX_HEIGHT_MM = 15.0, 300.0

_MIN_VERTICES = 30


def load_stl_mesh(raw_bytes: bytes) -> trimesh.Trimesh:
    """Load a .stl file as a real triangle mesh (faces + normals kept).

    `trimesh.load(..., file_type="stl")` handles both binary and ASCII STL,
    and on unparseable input returns an empty `Scene` rather than raising —
    checked for explicitly below so callers get a clear ValueError instead of
    a confusing empty-scene object three calls later.
    """
    try:
        result = trimesh.load(io.BytesIO(raw_bytes), file_type="stl", process=True)
    except Exception as exc:
        raise ValueError(f"unrecognized_stl: {exc}") from exc
    if not isinstance(result, trimesh.Trimesh) or len(result.vertices) < _MIN_VERTICES:
        raise ValueError("unrecognized_stl")
    return result


def parse_stl(raw_bytes: bytes) -> dict:
    """Parse a single-side .stl scan into the same measurement shape as one
    element of scm_parser_service.parse_scm()'s "feet" list — minus "side",
    which the caller attaches based on which upload slot the file came from.

    Synchronous/CPU-bound, like parse_scm — run via asyncio.to_thread."""
    mesh = load_stl_mesh(raw_bytes)
    vertices = mesh.vertices
    x = vertices[:, 0].astype(float)
    y = vertices[:, 1].astype(float)
    z = vertices[:, 2].astype(float)

    keep = _strip_outlier_points(x, y, z)
    x, y, z = x[keep], y[keep], z[keep]

    length = float(y.max() - y.min())
    width = float(x.max() - x.min())
    height = float(z.max() - z.min())
    if not (_MIN_LENGTH_MM <= length <= _MAX_LENGTH_MM
            and _MIN_WIDTH_MM <= width <= _MAX_WIDTH_MM
            and _MIN_HEIGHT_MM <= height <= _MAX_HEIGHT_MM
            and length > width):
        raise ValueError("no_foot_geometry_found")

    block = FootBlock(byte_start=0, byte_end=len(raw_bytes), x=x, y=y, z=z)
    views = render_foot_views(block)
    ball_girth = block.ball_girth_mm
    instep_girth = _instep_girth(block)
    ball_line = _ball_line_mm(block.x, block.y)

    return {
        "point_count": block.point_count,
        "length_mm": round(block.length_mm, 1),
        "width_mm": round(block.width_mm, 1),
        "height_mm": round(block.height_mm, 1),
        "ball_girth_mm": round(ball_girth, 1) if ball_girth is not None else None,
        "instep_girth_mm": round(instep_girth, 1) if instep_girth is not None else None,
        "ball_line_mm": round(ball_line, 1) if ball_line is not None else None,
        "profile": extract_profile(block),
        "views_png": views,
    }
