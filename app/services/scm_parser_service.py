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
import zipfile
from dataclasses import dataclass, field

import numpy as np

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
#
# Uses matplotlib's object-oriented API (Figure + FigureCanvasAgg) directly
# rather than pyplot's plt.figure()/plt.show() — pyplot keeps a global
# "current figure" stack that isn't safe to touch from multiple threads at
# once, and this is called via asyncio.to_thread, so concurrent requests
# really can land in different worker threads simultaneously.

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure


def _scatter_view(u: np.ndarray, v: np.ndarray, depth: np.ndarray, *,
                   u_label: str, v_label: str, title: str,
                   invert_y: bool = False, figsize: tuple[float, float] = (5.0, 6.5)) -> bytes:
    """Render one 2D projection (u, v in mm) as a PNG, points colored by the
    third (unshown) axis for a cheap sense of depth. Real-world "up" (v
    increasing) is always plotted upward — matplotlib's default axis
    orientation already does this, so height (Z) views come out right-side
    up without any manual flip; `invert_y` is only for the top-down
    footprint view, where there's no physical up/down and toes-at-top just
    reads better."""
    fig = Figure(figsize=figsize, dpi=150)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ax.scatter(u, v, c=depth, cmap="viridis", s=1.5, alpha=0.5, linewidths=0, rasterized=True)
    ax.set_xlabel(f"{u_label}, мм")
    ax.set_ylabel(f"{v_label}, мм")
    ax.set_title(title, fontsize=10)
    ax.set_aspect("equal")
    ax.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    if invert_y:
        ax.invert_yaxis()
    fig.tight_layout()

    buf = io.BytesIO()
    canvas.print_png(buf)
    return buf.getvalue()


def render_foot_views(block: FootBlock) -> dict[str, bytes]:
    """Render top/side/front projections as PNG bytes."""
    return {
        "top": _scatter_view(
            block.x, block.y, block.z,
            u_label="ширина", v_label="длина", title="Вид сверху (footprint)",
            invert_y=True, figsize=(5.0, 6.5),
        ),
        "side": _scatter_view(
            block.y, block.z, block.x,
            u_label="длина", v_label="высота", title="Вид сбоку",
            figsize=(7.0, 4.0),
        ),
        "front": _scatter_view(
            block.x, block.z, block.y,
            u_label="ширина", v_label="высота", title="Вид спереди/сзади",
            figsize=(4.5, 4.5),
        ),
    }


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
