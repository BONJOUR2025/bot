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

    @property
    def ball_girth_mm(self) -> float | None:
        return _ball_girth(self.x, self.y, self.z)


def _strip_outlier_points(x: np.ndarray, y: np.ndarray, z: np.ndarray,
                           pctl_lo: float = 0.5, pctl_hi: float = 99.5,
                           margin_frac: float = 0.15) -> np.ndarray:
    """Boolean mask rejecting stray noise points (bad depth readings, sensor
    artifacts) that would otherwise blow out the bounding box.

    Some scans carry a small fraction (well under 1%) of wildly-off points —
    seen in the wild up to ~-1150mm on an otherwise normal ~280mm-long foot.
    A single such point makes a plain min/max bounding box anatomically
    implausible and gets the whole block rejected below, even though the
    other ~99.9% of points are a perfectly good foot. Percentile bounds with
    a margin are robust to that without needing to identify a specific
    sentinel value (there wasn't one — the observed outliers were scattered,
    not one fixed constant)."""
    keep = np.ones(len(x), dtype=bool)
    for coord in (x, y, z):
        p_lo, p_hi = np.percentile(coord, [pctl_lo, pctl_hi])
        margin = margin_frac * (p_hi - p_lo)
        keep &= (coord >= p_lo - margin) & (coord <= p_hi + margin)
    return keep


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
        keep = _strip_outlier_points(x, y, z)
        if keep.sum() < MIN_RUN_FLOATS // 3:  # would-be point count too low to trust
            continue
        x, y, z = x[keep], y[keep], z[keep]
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


# -- ball girth ("Пучки") ---------------------------------------------------
#
# A tape-measured ball girth wraps around two specific bony landmarks — the
# head of the 1st metatarsal (medial bulge, base of the big toe) and the
# head of the 5th metatarsal (lateral bulge, base of the little toe) — which
# are usually NOT at the same position along the foot's length. A single
# cross-section perpendicular to the length axis (what earlier versions of
# this module used) therefore systematically misses the true measurement:
# validated against two reference scans with known ball-girth readings from
# the scanner's own software, that gave errors of 3-9mm and inconsistent
# results between the two feet of the same person.
#
# This instead:
#  1. locates the medial and lateral bulges independently (each is the
#     widest point on its own side, searched only in the 50-80% length
#     window to avoid the toe tips — a big toe often sticks out further
#     medially than the actual metatarsal head, which would otherwise get
#     picked up as a false landmark);
#  2. cuts a thin slab through both landmark points, angled to match the
#     line between them (not perpendicular to the length axis) — this is
#     what makes it different from a plain cross-section;
#  3. measures the perimeter of the convex hull of that slab, projected
#     into its own plane, as a stand-in for the tape wrapping around the
#     foot at that oblique cut.
#
# Calibrated against the two reference scans to within 1.6-3.6mm (one
# outlier at -2.3mm) — good enough to show as an estimate, not a
# certified measurement (see module docstring).

_BALL_ZONE_PCT = (50.0, 80.0)  # search window for landmarks, % of foot length from heel
_BALL_LANDMARK_PERCENTILE = 98.0  # robust "extreme" point per length-bin (vs single-point max/min)
_BALL_SLAB_FRAC = 0.002  # slab half-thickness as a fraction of foot length


def _convex_hull_2d(points: np.ndarray) -> np.ndarray:
    """Monotone-chain convex hull of a 2D point set (no scipy dependency)."""
    pts = sorted(set(map(tuple, points)))
    if len(pts) < 3:
        return np.array(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def _hull_perimeter(points: np.ndarray) -> float | None:
    hull = _convex_hull_2d(points)
    if len(hull) < 3:
        return None
    edges = np.diff(np.vstack([hull, hull[:1]]), axis=0)
    return float(np.sum(np.hypot(edges[:, 0], edges[:, 1])))


def _find_ball_landmarks(x: np.ndarray, y: np.ndarray, ymin: float, ymax: float,
                          nbins: int = 100) -> tuple[np.ndarray, np.ndarray] | None:
    """Find the medial and lateral metatarsal-head bulges as (x, y) points."""
    edges = np.linspace(ymin, ymax, nbins + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    medial = np.full(nbins, np.nan)
    lateral = np.full(nbins, np.nan)
    for j in range(nbins):
        mask = (y >= edges[j]) & (y < edges[j + 1])
        if mask.sum() < 5:
            continue
        xs = x[mask]
        medial[j] = np.percentile(xs, _BALL_LANDMARK_PERCENTILE)
        lateral[j] = np.percentile(xs, 100 - _BALL_LANDMARK_PERCENTILE)

    pct = (centers - ymin) / (ymax - ymin) * 100
    zone = (pct >= _BALL_ZONE_PCT[0]) & (pct <= _BALL_ZONE_PCT[1])
    idx = np.where(zone)[0]
    if not idx.size or np.all(np.isnan(medial[idx])) or np.all(np.isnan(lateral[idx])):
        return None
    i_med = idx[np.nanargmax(medial[idx])]
    i_lat = idx[np.nanargmin(lateral[idx])]
    return np.array([medial[i_med], centers[i_med]]), np.array([lateral[i_lat], centers[i_lat]])


def _ball_girth(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> float | None:
    ymin, ymax = float(y.min()), float(y.max())
    length = ymax - ymin
    landmarks = _find_ball_landmarks(x, y, ymin, ymax)
    if landmarks is None:
        return None
    p_medial, p_lateral = landmarks

    direction = p_medial - p_lateral
    norm = np.linalg.norm(direction)
    if norm < 1e-6:
        return None
    direction = direction / norm
    normal = np.array([-direction[1], direction[0]])
    origin = (p_medial + p_lateral) / 2

    rel_xy = np.column_stack([x, y]) - origin
    signed_dist = rel_xy @ normal
    slab = np.abs(signed_dist) < length * _BALL_SLAB_FRAC
    if slab.sum() < 15:
        return None

    u = rel_xy[slab] @ direction  # in-plane horizontal coordinate
    v = z[slab]  # height, already vertical
    return _hull_perimeter(np.column_stack([u, v]))


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
    # Byte position in the file, not point count, carries the left/right
    # identity: on both reference scans used to validate this parser, the
    # scanner wrote the left foot's point cloud before the right foot's,
    # consistently, regardless of which one ended up with more points.
    # (Point-count ordering was tried first and shuffled L/R at random
    # between scans — same file structure, no reliable meaning.)
    blocks.sort(key=lambda b: b.byte_start)

    feet = []
    for i, block in enumerate(blocks):
        views = render_foot_views(block)
        ball_girth = block.ball_girth_mm
        side = None
        if len(blocks) == 2:
            side = "left" if i == 0 else "right"
        feet.append({
            "side": side,
            "byte_range": [block.byte_start, block.byte_end],
            "point_count": block.point_count,
            "length_mm": round(block.length_mm, 1),
            "width_mm": round(block.width_mm, 1),
            "height_mm": round(block.height_mm, 1),
            "ball_girth_mm": round(ball_girth, 1) if ball_girth is not None else None,
            "views_png": {k: v for k, v in views.items()},
        })

    return {"metadata": metadata, "feet": feet, "file_size": len(data)}
