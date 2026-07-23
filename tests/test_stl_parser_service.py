"""Tests for stl_parser_service — synthetic geometry only, no real client scans."""
from __future__ import annotations

import struct

import numpy as np
import pytest

from app.services.stl_parser_service import parse_stl

RNG = np.random.default_rng(42)


def _half_width(y_frac: np.ndarray) -> np.ndarray:
    """Rough foot-shaped taper: narrow at heel/toe, widest ~65% of length."""
    return 20.0 + 20.0 * np.exp(-((y_frac - 0.65) ** 2) / (2 * 0.2 ** 2))


def _half_height(y_frac: np.ndarray) -> np.ndarray:
    return 20.0 + 15.0 * np.exp(-((y_frac - 0.35) ** 2) / (2 * 0.25 ** 2))


def _make_foot_points(n: int = 8000, length_mm: float = 250.0) -> np.ndarray:
    y = RNG.uniform(0.0, length_mm, n)
    frac = y / length_mm
    hw = _half_width(frac)
    hh = _half_height(frac)
    x = RNG.uniform(-1.0, 1.0, n) * hw
    z = RNG.uniform(0.0, 1.0, n) * hh
    return np.column_stack([x, y, z]).astype(np.float32)


def _make_binary_stl(points: np.ndarray) -> bytes:
    """Wrap each point as a degenerate (zero-area) triangle — parse_stl only
    reads vertex positions, never face topology, so this is a valid, minimal
    way to encode an arbitrary point cloud as binary STL."""
    n = len(points)
    header = b"\x00" * 80
    body = bytearray()
    zero_normal = struct.pack("<3f", 0.0, 0.0, 0.0)
    for p in points:
        vert = struct.pack("<3f", float(p[0]), float(p[1]), float(p[2]))
        body += zero_normal + vert + vert + vert + struct.pack("<H", 0)
    return header + struct.pack("<I", n) + bytes(body)


def test_parse_stl_returns_sane_measurements():
    points = _make_foot_points(length_mm=250.0)
    raw = _make_binary_stl(points)

    result = parse_stl(raw)

    assert 240.0 <= result["length_mm"] <= 260.0
    assert 30.0 <= result["width_mm"] <= 100.0
    assert 15.0 <= result["height_mm"] <= 80.0
    assert result["point_count"] > 1000

    profile = result["profile"]
    assert profile["length_mm"] == pytest.approx(result["length_mm"], abs=1.0)
    assert len(profile["y"]) == profile["n"]
    assert any(v is not None for v in profile["medial"])


def test_parse_stl_rejects_garbage_bytes():
    with pytest.raises(ValueError):
        parse_stl(b"not a valid stl file" * 10)


def test_parse_stl_rejects_non_foot_geometry():
    # A small cube — finite/small-magnitude but not anatomically foot-shaped
    # (too short, and not longer than it is wide).
    points = RNG.uniform(0.0, 20.0, size=(200, 3)).astype(np.float32)
    raw = _make_binary_stl(points)
    with pytest.raises(ValueError):
        parse_stl(raw)
