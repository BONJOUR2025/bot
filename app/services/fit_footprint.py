"""Top-view footprint overlay: the foot's outline against the shoe cavity's.

The one 2D picture kept in the redesigned UI. It answers the question a fitter
actually asks first -- "where does the foot stick out past the shoe?" -- which
a table of millimetres does not convey at a glance.

Drawn from the *meshes* the fit_v3 pipeline already registered, not from
slice_v1's profile arrays, so the picture and the numbers beside it come from
one source. The cavity (not the last) is the grey shape, matching what the
verdict is computed against.
"""
from __future__ import annotations

import base64
import io

import numpy as np
import trimesh
from matplotlib.figure import Figure

# Outlines are read from the tread band only. Higher up, the ankle bones bulge
# past the footprint on the foot and the last flares for the topline -- neither
# belongs in a "where does the sole sit" picture. Same reasoning as
# FOOTPRINT_HEIGHT_MM in scm_parser_service.
_TREAD_HEIGHT_MM = 30.0
_N_BINS = 140
_MIN_POINTS_PER_BIN = 4
# A protrusion has to clear the measurement noise before it is drawn as a
# conflict (§13.6) -- see fit_clearance for the budget this mirrors.
_PROTRUSION_MM = 2.5


def _outline(mesh: trimesh.Trimesh, edges: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Medial (max X) and lateral (min X) edge per length bin, NaN where the
    shape does not reach that bin."""
    v = np.asarray(mesh.vertices, dtype=float)
    band = v[v[:, 2] <= v[:, 2].min() + _TREAD_HEIGHT_MM]
    y, x = band[:, 1], band[:, 0]
    medial = np.full(len(edges) - 1, np.nan)
    lateral = np.full(len(edges) - 1, np.nan)
    for i, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        m = (y >= lo) & (y < hi)
        if m.sum() < _MIN_POINTS_PER_BIN:
            continue
        medial[i] = np.percentile(x[m], 99)
        lateral[i] = np.percentile(x[m], 1)
    return medial, lateral


def render_footprint_overlay(foot_mesh: trimesh.Trimesh,
                             cavity_mesh: trimesh.Trimesh) -> str | None:
    """PNG (base64, no data: prefix) of the foot outline over the cavity."""
    fv, cv = np.asarray(foot_mesh.vertices), np.asarray(cavity_mesh.vertices)
    y_lo = float(min(fv[:, 1].min(), cv[:, 1].min()))
    y_hi = float(max(fv[:, 1].max(), cv[:, 1].max()))
    if y_hi <= y_lo:
        return None
    edges = np.linspace(y_lo, y_hi, _N_BINS + 1)
    centres = (edges[:-1] + edges[1:]) / 2.0

    foot_med, foot_lat = _outline(foot_mesh, edges)
    cav_med, cav_lat = _outline(cavity_mesh, edges)

    # Where the foot's own edge lies outside the cavity's, on either side.
    with np.errstate(invalid="ignore"):
        out_med = (foot_med - cav_med) > _PROTRUSION_MM
        out_lat = (cav_lat - foot_lat) > _PROTRUSION_MM

    fig = Figure(figsize=(4.0, 6.6), dpi=140)
    ax = fig.add_subplot(111)
    ok = ~np.isnan(cav_med) & ~np.isnan(cav_lat)
    ax.fill_betweenx(centres[ok], cav_lat[ok], cav_med[ok], color="0.85",
                     label="полость обуви")
    ax.plot(foot_med, centres, "b-", lw=1.5, label="стопа")
    ax.plot(foot_lat, centres, "b-", lw=1.5)
    if out_med.any():
        ax.plot(foot_med[out_med], centres[out_med], "r.", ms=5, zorder=5)
    if out_lat.any():
        ax.plot(foot_lat[out_lat], centres[out_lat], "r.", ms=5, zorder=5)

    ax.set_title("След стопы и след колодки (сверху)", fontsize=9)
    ax.set_xlabel("ширина, мм")
    ax.set_ylabel("длина от пятки, мм")
    ax.set_aspect("equal")
    ax.legend(fontsize=7, loc="lower right")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return base64.b64encode(buf.getvalue()).decode("ascii")
