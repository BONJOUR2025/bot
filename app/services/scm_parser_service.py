"""Parser for .scm foot-scan files (proprietary format, undocumented).

.scm is a ZIP container holding one file with a small text header
(name/phone/scan id/date, UTF-16LE) followed by several megabytes of
binary mesh data with no documented layout. There is no public spec for
this format, so this module does NOT decode it structurally — instead it:

1. Pulls out the header metadata by scanning for printable UTF-16LE runs
   (ASCII + Cyrillic) — this part is reliable, the header is plain text.
2. Finds the foot point cloud(s) by scanning the whole file for stretches
   where reading every 4 bytes as a little-endian float32 gives finite,
   small-magnitude numbers (millimeter-scale). Real geometry data behaves
   this way; essentially all other byte patterns (compressed data, text,
   random binary) do not, so a long run of "plausible" floats is strong
   evidence of an aligned XYZ vertex array — confirmed by manual
   inspection: the recovered points render as an anatomically correct
   foot (toes, arch, heel) and the resulting length matched a sane shoe
   size. This is a heuristic, not a documented format, so results should
   be read as "best effort" rather than certified measurements.
"""
from __future__ import annotations

import io
import re
import struct
import zipfile
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

# -- metadata extraction -----------------------------------------------

_UTF16LE_ASCII_OR_CYRILLIC = re.compile(
    rb"(?:[\x20-\x7e]\x00|[\x00-\xff]\x04){3,}"
)


def _decode_utf16le_runs(data: bytes) -> list[tuple[int, str]]:
    """Find printable UTF-16LE string runs (ASCII + Cyrillic block only —
    everything this scanner's header actually uses), length >= 3 chars."""
    results: list[tuple[int, str]] = []
    for m in _UTF16LE_ASCII_OR_CYRILLIC.finditer(data):
        raw = m.group(0)
        try:
            text = raw.decode("utf-16-le")
        except UnicodeDecodeError:
            continue
        results.append((m.start(), text))
    return results


def extract_metadata(data: bytes) -> dict:
    """Best-effort extraction of the scan's header fields.

    The header is a short run of small UTF-16LE strings near the start of
    the file (name, phone, an internal scan id, a date, a time, and what
    looks like a birth date) — there's no explicit field tagging, so
    fields are told apart by shape (a date-like string, a digits-only
    string of typical phone length, etc.) rather than by position, since
    position could plausibly shift between scanner software versions.
    """
    strings = _decode_utf16le_runs(data[:4096])
    meta: dict = {
        "name": None,
        "phone": None,
        "scan_id": None,
        "scan_date": None,
        "scan_time": None,
        "birth_date": None,
        "raw_strings": [s for _, s in strings],
    }
    date_re = re.compile(r"^\d{4}/\d{2}/\d{2}$")
    dob_re = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
    time_re = re.compile(r"^\d{2}:\d{2}:\d{2}$")
    phone_re = re.compile(r"^\d{10,11}$")
    name_re = re.compile(r"^[A-Za-zА-Яа-яЁё]{2,}$")

    for _, s in strings:
        s = s.strip()
        if not s:
            continue
        # a combined "<scan_id><date>" run (no separator in the source
        # data) — split off the trailing date if present.
        m = re.search(r"(\d{4}/\d{2}/\d{2})$", s)
        if m and not date_re.match(s):
            meta["scan_date"] = meta["scan_date"] or m.group(1)
            prefix = s[: m.start()]
            if prefix and meta["scan_id"] is None:
                meta["scan_id"] = prefix
            continue
        if date_re.match(s) and meta["scan_date"] is None:
            meta["scan_date"] = s
        elif dob_re.match(s) and meta["birth_date"] is None:
            meta["birth_date"] = s
        elif time_re.match(s) and meta["scan_time"] is None:
            meta["scan_time"] = s
        elif phone_re.match(s) and meta["phone"] is None:
            meta["phone"] = s
        elif name_re.match(s) and meta["name"] is None:
            meta["name"] = s
    return meta


# -- point cloud extraction ----------------------------------------------

PLAUSIBLE_MAX_MM = 2000.0  # generous bound: real foot/leg geometry is a
                           # few hundred mm; this just needs to reject
                           # garbage, not be a tight anatomical fit.
MIN_RUN_FLOATS = 9000      # >= ~3000 XYZ points — small spurious matches
                           # (padding, text runs) don't get anywhere close
                           # to this long a contiguous "plausible" stretch.


def _find_plausible_runs(arr: np.ndarray) -> list[tuple[int, int]]:
    """Return (start, end) index ranges (in `arr`, i.e. float units) where
    every value is finite and small-magnitude, run length >= MIN_RUN_FLOATS."""
    mask = np.isfinite(arr) & (np.abs(arr) < PLAUSIBLE_MAX_MM)
    if not mask.any():
        return []
    padded = np.concatenate(([False], mask, [False]))
    diffs = np.diff(padded.astype(np.int8))
    starts = np.where(diffs == 1)[0]
    ends = np.where(diffs == -1)[0]
    return [(s, e) for s, e in zip(starts, ends) if e - s >= MIN_RUN_FLOATS]


@dataclass
class FootBlock:
    byte_start: int
    byte_end: int
    x: np.ndarray = field(repr=False)
    y: np.ndarray = field(repr=False)
    z: np.ndarray = field(repr=False)

    @property
    def point_count(self) -> int:
        return len(self.x)

    @property
    def length_mm(self) -> float:
        return float(self.y.max() - self.y.min())

    @property
    def width_mm(self) -> float:
        return float(self.x.max() - self.x.min())

    @property
    def height_mm(self) -> float:
        return float(self.z.max() - self.z.min())


def find_foot_blocks(data: bytes) -> list[FootBlock]:
    """Scan the whole file for aligned float32 XYZ point-cloud blocks.

    float32 arrays could start at any byte offset, so all 4 possible
    alignments ("phases") are checked. Overlapping candidates across
    phases are deduplicated, keeping the longest run per byte region.
    """
    n = len(data)
    candidates: list[tuple[int, int, int]] = []  # (byte_start, byte_end, phase)
    for phase in range(4):
        usable = (n - phase) - ((n - phase) % 4)
        if usable <= MIN_RUN_FLOATS * 4:
            continue
        arr = np.frombuffer(data, dtype="<f4", count=usable // 4, offset=phase)
        for s, e in _find_plausible_runs(arr):
            candidates.append((phase + s * 4, phase + e * 4, phase))

    # keep only non-overlapping candidates, longest first
    candidates.sort(key=lambda c: c[1] - c[0], reverse=True)
    kept: list[tuple[int, int, int]] = []
    for c in candidates:
        cs, ce, _ = c
        if any(not (ce <= ks or cs >= ke) for ks, ke, _ in kept):
            continue  # overlaps an already-kept, larger block
        kept.append(c)
    kept.sort(key=lambda c: c[0])

    blocks: list[FootBlock] = []
    for byte_start, byte_end, phase in kept:
        span = data[byte_start:byte_end]
        ntriples = len(span) // 12
        usable_bytes = ntriples * 12
        flat = np.frombuffer(span[:usable_bytes], dtype="<f4")
        xyz = flat.reshape(-1, 3)
        x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
        width = float(x.max() - x.min())
        length = float(y.max() - y.min())
        height = float(z.max() - z.min())
        # A degenerate block (header padding, an unrelated matrix/texture
        # array that happens to pass the finite/small-magnitude check over
        # a long run) is NOT rejected by "finite and small" alone — e.g. a
        # ~1000mm cube-shaped block turned up here in testing. A real foot
        # is anatomically bounded (adult foot length ~150-400mm, always
        # longer than it is wide) and NOT roughly cube-shaped, so filter
        # on that instead of a generic "has some extent" check.
        if not (100 <= length <= 400 and 30 <= width <= 200 and 15 <= height <= 300):
            continue
        if length <= width:
            continue
        blocks.append(FootBlock(byte_start, byte_end, x, y, z))
    return blocks


# -- visualization ---------------------------------------------------------

def _rasterize(u: np.ndarray, v: np.ndarray, width: int = 420, height: int = 560,
               margin: int = 20, invert_v: bool = False) -> Image.Image:
    """Render a 2D point scatter (u, v in mm) to a PIL image, point density
    as grayscale (darker = more points at that pixel — cheap way to get an
    anti-aliased-looking silhouette without per-point draw calls)."""
    u_range = max(u.max() - u.min(), 1.0)
    v_range = max(v.max() - v.min(), 1.0)
    scale = min((width - 2 * margin) / u_range, (height - 2 * margin) / v_range)

    px = ((u - u.min()) * scale + margin).astype(np.int32)
    py = ((v - v.min()) * scale + margin).astype(np.int32)
    if invert_v:
        py = height - py
    px = np.clip(px, 0, width - 1)
    py = np.clip(py, 0, height - 1)

    canvas = np.zeros((height, width), dtype=np.int32)
    # Splat each point onto a 2x2 neighborhood, not a single pixel — a
    # scan has tens of thousands of points but a few hundred px of canvas,
    # so single-pixel dots left visible gaps between samples that made the
    # silhouette look washed out. 2x2 closes those gaps without needing a
    # slower proper circular brush.
    for dy in (0, 1):
        for dx in (0, 1):
            yy = np.clip(py + dy, 0, height - 1)
            xx = np.clip(px + dx, 0, width - 1)
            np.add.at(canvas, (yy, xx), 1)
    # This is a surface projection, not a curve — most touched pixels get
    # hit only a handful of times (points spread over the whole silhouette
    # area, not piled onto a thin outline), so scaling darkness purely by
    # hit count made the whole shape pale gray instead of a solid-looking
    # silhouette. Give every touched pixel a dark floor (~55%) regardless
    # of count, then let count only push the darkest areas the rest of
    # the way to black — reads as a clean solid outline instead of haze.
    hit = canvas > 0
    darkness = np.zeros(canvas.shape, dtype=np.float64)
    if hit.any():
        log_density = np.log1p(canvas[hit].astype(np.float64))
        normalized = log_density / log_density.max() if log_density.max() > 0 else log_density
        darkness[hit] = 0.55 + 0.45 * normalized
    gray = (255 - (darkness * 255)).astype(np.uint8)
    return Image.fromarray(gray, mode="L").convert("RGB")


def render_foot_views(block: FootBlock) -> dict[str, bytes]:
    """Render top/side/front projections as PNG bytes."""
    views = {
        "top": _rasterize(block.x, block.y, invert_v=True),      # footprint: width x length
        "side": _rasterize(block.y, block.z, width=560, height=280),   # length x height
        "front": _rasterize(block.x, block.z, width=280, height=280),  # width x height
    }
    out = {}
    for name, img in views.items():
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out[name] = buf.getvalue()
    return out


# -- top-level entry point --------------------------------------------------

def parse_scm(raw_bytes: bytes) -> dict:
    """Parse a .scm file (ZIP-wrapped) into metadata + per-foot measurements
    + rendered views. Synchronous/CPU-bound — callers should run this via
    asyncio.to_thread rather than await it directly on the event loop."""
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        names = zf.namelist()
        if not names:
            raise ValueError("empty_archive")
        data = zf.read(names[0])

    metadata = extract_metadata(data)
    blocks = find_foot_blocks(data)
    # largest blocks first — the real foot/leg scans dwarf any incidental
    # smaller plausible-looking stretch that might slip through.
    blocks.sort(key=lambda b: b.point_count, reverse=True)

    feet = []
    for block in blocks:
        views = render_foot_views(block)
        feet.append({
            "byte_range": [block.byte_start, block.byte_end],
            "point_count": block.point_count,
            "length_mm": round(block.length_mm, 1),
            "width_mm": round(block.width_mm, 1),
            "height_mm": round(block.height_mm, 1),
            "views_png": {k: v for k, v in views.items()},
        })

    return {"metadata": metadata, "feet": feet, "file_size": len(data)}
