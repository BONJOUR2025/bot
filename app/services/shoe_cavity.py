"""Estimated inner cavity of a finished shoe -- §7 of research_foot_last_pose_
fit_technical_report_for_claude.md.

The foot never meets the last: it meets the inside of a shoe *built on* that
last, which is smaller by everything in between -- insole underfoot, lining
throughout, a stiffened counter at the heel, a toe puff at the front. §7.3
forbids treating the last surface itself as the cavity, and §26.11 lists
"сравнение стопы с внешней условной оболочкой обуви" among the things to
remove. Comparing directly against the last systematically *understates*
tightness, because every one of those layers eats into the space the foot
actually gets.

With no construction data available this builds the §7.2 proxy:

    C_proxy = LastSurface + regional_offset_field

offsets applied inward along the surface normal, region by region, and the
result is labelled `cavity_mode = LAST_PROXY` so no downstream report can
present it as a measured shoe interior. §7.2's own sign convention is followed:
the sole moves *up* by the insole thickness (the foot sits on top of it), while
heel, toe and vamp move *inward*.

Deliberately not modelled: the lacing zone. §7.2 calls it a parametric boundary
rather than a rigid surface, and inventing a fixed wall there would be exactly
the false precision the report objects to. It is reported as an unmodelled
region instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh

# Default construction allowances for men's classic leather footwear, in mm.
# Starting values from §7.2's own list of layers -- explicitly not calibrated
# against real shoes (§29 asks for a fitting pilot before any threshold is
# treated as fact), so they are reported alongside the geometry.
DEFAULT_CONSTRUCTION = {
    "insole_thickness_mm": 2.0,
    "lining_thickness_mm": 1.0,
    "heel_counter_thickness_mm": 1.5,
    "toe_puff_thickness_mm": 1.2,
}

# Region boundaries as fractions of the last's length (heel = 0).
_HEEL_REGION_MAX = 0.25
_TOE_REGION_MIN = 0.80
# Anything whose normal points more downward than this counts as sole.
_SOLE_NORMAL_Z = -0.5


@dataclass
class CavityModel:
    mesh: trimesh.Trimesh
    cavity_mode: str
    construction: dict
    offsets_applied_mm: dict
    unmodelled_regions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "cavity_mode": self.cavity_mode,
            "construction": dict(self.construction),
            "offsets_applied_mm": {k: round(v, 2) for k, v in self.offsets_applied_mm.items()},
            "unmodelled_regions": list(self.unmodelled_regions),
            "warnings": list(self.warnings),
            "is_measured_shoe_interior": False,
        }


def _region_offsets(mesh: trimesh.Trimesh, construction: dict) -> np.ndarray:
    """Per-vertex inward offset in mm, by anatomical region (§7.2)."""
    v = np.asarray(mesh.vertices, dtype=float)
    y = v[:, 1]
    y_min, y_max = float(y.min()), float(y.max())
    length = max(y_max - y_min, 1e-6)
    frac = (y - y_min) / length

    normals = np.asarray(mesh.vertex_normals, dtype=float)
    is_sole = normals[:, 2] < _SOLE_NORMAL_Z

    lining = construction["lining_thickness_mm"]
    offsets = np.full(len(v), lining, dtype=float)          # vamp//general lining
    offsets[frac <= _HEEL_REGION_MAX] = lining + construction["heel_counter_thickness_mm"]
    offsets[frac >= _TOE_REGION_MIN] = lining + construction["toe_puff_thickness_mm"]
    # The sole is the one region that is not "lining inward": the foot stands on
    # top of the insole, so the floor of the cavity rises by its thickness.
    offsets[is_sole] = construction["insole_thickness_mm"]
    return offsets


def build_cavity(
    last_mesh: trimesh.Trimesh,
    construction: dict | None = None,
    cavity_mode: str = "LAST_PROXY",
) -> CavityModel:
    """Inner cavity estimated from a last. Returns a new mesh; `last_mesh` is
    left untouched (§19.1)."""
    warnings: list[str] = []
    cfg = {**DEFAULT_CONSTRUCTION, **(construction or {})}

    cavity = last_mesh.copy()
    try:
        normals = np.asarray(cavity.vertex_normals, dtype=float)
    except Exception:
        return CavityModel(cavity, cavity_mode, cfg, {}, [], ["vertex_normals_unavailable"])

    offsets = _region_offsets(cavity, cfg)
    # Inward = against the outward surface normal. The sole's own normal points
    # down, so moving against it lifts the floor -- which is the wanted sign.
    cavity.vertices = np.asarray(cavity.vertices, dtype=float) - normals * offsets[:, None]

    if not cavity.is_watertight and last_mesh.is_watertight:
        warnings.append("offset_broke_watertightness")

    applied = {
        "sole_up": cfg["insole_thickness_mm"],
        "heel_inward": cfg["lining_thickness_mm"] + cfg["heel_counter_thickness_mm"],
        "toe_inward": cfg["lining_thickness_mm"] + cfg["toe_puff_thickness_mm"],
        "vamp_inward": cfg["lining_thickness_mm"],
    }
    return CavityModel(
        mesh=cavity,
        cavity_mode=cavity_mode,
        construction=cfg,
        offsets_applied_mm=applied,
        # §7.2: the closure is a parametric range, not a surface. Saying so is
        # more honest than drawing a wall where the laces would be.
        unmodelled_regions=["lacing_closure"],
        warnings=warnings,
    )
