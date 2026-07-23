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
"""
from __future__ import annotations

import struct

import numpy as np

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

_BINARY_TRIANGLE_DTYPE = np.dtype([
    ("normal", "<f4", 3),
    ("v1", "<f4", 3),
    ("v2", "<f4", 3),
    ("v3", "<f4", 3),
    ("attr", "<u2"),
])


def _read_binary_stl(data: bytes) -> np.ndarray | None:
    """Binary STL: 80-byte header, uint32 triangle count, then 50 bytes per
    triangle (normal + 3 vertices as float32, + a 2-byte attribute count).
    The byte-count check below (rather than sniffing the header) is what
    actually confirms this is binary — an ASCII STL's header also happens to
    be 80+ bytes, so only the header alone can't tell the two apart."""
    if len(data) < 84:
        return None
    ntri = struct.unpack_from("<I", data, 80)[0]
    if 84 + ntri * 50 != len(data):
        return None
    tri = np.frombuffer(data, dtype=_BINARY_TRIANGLE_DTYPE, count=ntri, offset=84)
    return np.vstack([tri["v1"], tri["v2"], tri["v3"]])


def _read_ascii_stl(data: bytes) -> np.ndarray | None:
    """Fallback for ASCII STL (`solid ... facet normal ... vertex x y z ...`),
    in case some future export uses it instead of binary."""
    try:
        text = data.decode("ascii", errors="ignore")
    except Exception:
        return None
    verts: list[list[float]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("vertex"):
            continue
        parts = line.split()
        if len(parts) != 4:
            continue
        try:
            verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
        except ValueError:
            continue
    if not verts:
        return None
    return np.array(verts, dtype=np.float32)


def parse_stl(raw_bytes: bytes) -> dict:
    """Parse a single-side .stl scan into the same measurement shape as one
    element of scm_parser_service.parse_scm()'s "feet" list — minus "side",
    which the caller attaches based on which upload slot the file came from.

    Synchronous/CPU-bound, like parse_scm — run via asyncio.to_thread."""
    vertices = _read_binary_stl(raw_bytes)
    if vertices is None:
        vertices = _read_ascii_stl(raw_bytes)
    if vertices is None or len(vertices) < 30:
        raise ValueError("unrecognized_stl")

    vertices = np.unique(vertices, axis=0)
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
