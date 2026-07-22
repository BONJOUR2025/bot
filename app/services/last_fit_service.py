"""Compare a foot scan against a shoe-last (колодка) scan and explain fit.

Rather than comparing a handful of scalar girths, this aligns the foot and the
last (both anchored at the heel by the scanner) and walks along the length
section by section, checking at each cross-section whether the foot fits inside
the last and how much room (ease) there is. The result is:

  * an overall verdict + per-zone verdicts (пятка / свод / подъём / пучки /
    носок), each phrased as a *consequence for the client* — what actually
    happens to the foot, not just a number;
  * an "overlap" score — how much of the foot's outline sits inside the last;
  * two overlay images (footprint + side profile) with the foot drawn inside
    the last and the problem zones highlighted in red.

Allowances (how much bigger than the foot a last should be) are not invented —
they come from ГОСТ 3927-88 ("Колодки обувные", min 5-10 mm length allowance)
and bespoke-lastmaking sources (3DShoemaker / PodoHub: ~13 mm typical length,
~10-12 mm ball-girth ease, comfortable up to ~12 mm at the ball).

Width (bounding box) is used only for the visual overlay, not for the numeric
girth verdict — see scm_parser_service's module docstring on why the raw
bounding box isn't a calibrated measurement.
"""
from __future__ import annotations

import base64
import io

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

# -- allowances / thresholds (mm) ------------------------------------------

LENGTH_MIN = 5.0        # below this the toe has nowhere to go
LENGTH_TIGHT = 8.0
LENGTH_IDEAL_MAX = 15.0
LENGTH_LOOSE = 22.0

# per-zone minimum comfortable girth ease (last girth − foot girth)
ZONE_GIRTH_MIN = {"ball": 6.0, "instep": 5.0, "waist": 2.0, "heel": -2.0}
ZONE_GIRTH_LOOSE = {"ball": 16.0, "instep": 16.0, "waist": 18.0, "heel": 12.0}

# a foot edge poking this far (mm) past the last outline counts as a hard clash
PROTRUSION_MM = 2.0

# zones as fractions of FOOT length, heel = 0
ZONES = [
    ("heel", 0.00, 0.25, "Пятка"),
    ("waist", 0.25, 0.42, "Свод / талия"),
    ("instep", 0.42, 0.60, "Подъём"),
    ("ball", 0.60, 0.78, "Пучки (широкая часть)"),
    ("toe", 0.78, 1.00, "Носок (пальцы)"),
]


# -- profile helpers --------------------------------------------------------

def _arr(profile: dict, key: str) -> np.ndarray:
    return np.array([np.nan if v is None else v for v in profile[key]], dtype=float)


def _mirror_profile(profile: dict) -> dict:
    """Flip a last from one foot to the other (lasts are mirror-identical):
    x → −x turns the medial edge into the negated lateral edge and vice versa."""
    medial = _arr(profile, "medial")
    lateral = _arr(profile, "lateral")
    out = dict(profile)
    out["medial"] = list(np.where(np.isnan(lateral), np.nan, -lateral))
    out["lateral"] = list(np.where(np.isnan(medial), np.nan, -medial))
    return out


def _resample(profile: dict, y_target: np.ndarray) -> dict:
    """Interpolate a profile's per-section arrays onto y_target (mm from heel)."""
    y = _arr(profile, "y")
    out = {"y": y_target}
    for key in ("medial", "lateral", "top", "girth"):
        vals = _arr(profile, key)
        ok = ~np.isnan(vals)
        out[key] = np.interp(y_target, y[ok], vals[ok]) if ok.sum() >= 2 else np.full_like(y_target, np.nan)
    return out


# -- consequence phrasing ---------------------------------------------------

def _length_consequence(ease: float) -> tuple[str, str]:
    if ease < LENGTH_MIN:
        return "too_tight", (
            "Колодка короче или впритык по длине — пальцы упрутся в носок, "
            "большой палец и ноготь будут травмироваться, со временем возможна "
            "деформация. Клиенту будет тесно и больно при ходьбе."
        )
    if ease < LENGTH_TIGHT:
        return "tight_ok", (
            "Запас по длине минимальный — для тонкой/летней обуви приемлемо, но "
            "для закрытой обуви пальцам будет тесновато, особенно к вечеру когда "
            "стопа отекает."
        )
    if ease <= LENGTH_IDEAL_MAX:
        return "ideal", "Запас по длине комфортный — пальцам есть куда двигаться при шаге."
    if ease <= LENGTH_LOOSE:
        return "loose_ok", (
            "Запас по длине больше обычного — обувь чуть великовата, при активной "
            "ходьбе стопа может немного проскальзывать вперёд."
        )
    return "too_loose", (
        "Колодка заметно длиннее стопы — обувь будет велика, стопа поедет вперёд, "
        "пятка начнёт выскакивать, появятся натёртости."
    )


_ZONE_TIGHT = {
    "heel": "В пятке колодка уже стопы — задник будет давить и натирать пятку, "
            "возможны мозоли по краю пятки.",
    "waist": "В своде колодка поджимает — обувь будет давить по центру стопы, "
             "ощущение сжатия, особенно у людей с высоким сводом.",
    "instep": "Подъём колодки ниже подъёма стопы — верх обуви и шнуровка будут "
              "врезаться в подъём, давить на сухожилия и сосуды, нога быстро "
              "устаёт и немеет.",
    "ball": "В пучках (самое широкое место) колодка уже стопы — будет сдавливать "
            "косточки у основания большого пальца и мизинца, натирать, вызывать "
            "онемение пальцев; частая причина «жмёт в носке».",
    "toe": "В носке колодке не хватает объёма — пальцам тесно сверху и по бокам, "
           "они поджимаются, риск натоптышей и вросшего ногтя.",
}
_ZONE_LOOSE = {
    "heel": "В пятке колодка свободнее стопы — пятка не фиксируется и будет "
            "выскакивать при каждом шаге, обувь «хлопает».",
    "waist": "В своде многовато места — стопа слабо зафиксирована по центру.",
    "instep": "Подъём колодки выше подъёма стопы — верх обуви не прилегает, стопа "
              "не держится и скользит вперёд, теряется посадка.",
    "ball": "В пучках колодка заметно шире стопы — обувь болтается в самом важном "
            "месте, стопа гуляет вбок, снижается устойчивость.",
    "toe": "В носке очень много места — пальцы болтаются, но на здоровье это "
           "влияет мало (лучше слишком много, чем мало).",
}


# -- core comparison --------------------------------------------------------

def compare_profiles(foot: dict, last: dict, *, foot_side: str | None = None,
                     last_side: str | None = None) -> dict:
    """foot/last are shape profiles from scm_parser_service.extract_profile."""
    if foot_side and last_side and foot_side != last_side:
        last = _mirror_profile(last)

    foot_len = float(foot["length_mm"])
    last_len = float(last["length_mm"])
    y = _arr(foot, "y")
    y = y[y <= foot_len + 1e-6]
    f = _resample(foot, y)
    l = _resample(last, y)

    girth_ease = l["girth"] - f["girth"]           # >0: last roomier
    medial_ease = l["medial"] - f["medial"]        # >0: last edge outside foot
    lateral_ease = f["lateral"] - l["lateral"]     # >0: last edge outside foot
    top_ease = l["top"] - f["top"]                 # >0: last taller

    # containment: does the foot poke out of the last outline anywhere
    protr_width = np.fmax(np.fmax(-medial_ease, -lateral_ease), 0.0)
    protr_height = np.fmax(-top_ease, 0.0)
    protrusion = np.fmax(protr_width, protr_height)

    inside = np.nan_to_num(protrusion, nan=0.0) <= PROTRUSION_MM
    valid = ~np.isnan(protrusion)
    overlap_pct = round(100.0 * inside[valid].sum() / max(valid.sum(), 1), 1)

    length_ease = last_len - foot_len
    len_verdict, len_text = _length_consequence(length_ease)

    zones = []
    frac = y / foot_len
    for key, lo, hi, label in ZONES:
        sel = (frac >= lo) & (frac < hi) & valid
        if not sel.any():
            continue
        zg = girth_ease[sel]
        gmin = float(np.nanmin(zg)) if np.isfinite(zg).any() else None
        gmean = float(np.nanmean(zg)) if np.isfinite(zg).any() else None
        worst_protr = float(np.nanmax(protrusion[sel]))
        if key == "toe":
            verdict, text = len_verdict, len_text  # toe room ~ length verdict
        else:
            gmin_thr = ZONE_GIRTH_MIN[key]
            gloose_thr = ZONE_GIRTH_LOOSE[key]
            if worst_protr > PROTRUSION_MM or (gmin is not None and gmin < gmin_thr):
                verdict, text = "too_tight", _ZONE_TIGHT[key]
            elif gmean is not None and gmean > gloose_thr:
                verdict, text = "too_loose", _ZONE_LOOSE[key]
            else:
                verdict, text = "ideal", "Посадка в норме — колодка повторяет стопу с комфортным запасом."
        zones.append({
            "zone": key,
            "label": label,
            "verdict": verdict,
            "explanation": text,
            "girth_ease_min_mm": round(gmin, 1) if gmin is not None else None,
            "girth_ease_mean_mm": round(gmean, 1) if gmean is not None else None,
            "max_protrusion_mm": round(worst_protr, 1),
        })

    ranks = {"too_tight": 3, "tight_ok": 2, "too_loose": 1, "loose_ok": 1, "ideal": 0}
    worst = max((ranks.get(z["verdict"], 0) for z in zones), default=0)
    tight_zones = [z["label"] for z in zones if z["verdict"] == "too_tight"]
    loose_zones = [z["label"] for z in zones if z["verdict"] == "too_loose"]
    if worst >= 3:
        overall = "not_fit"
        overall_text = ("Колодка не подойдёт: тесно в зонах — " + ", ".join(tight_zones) +
                        ". В этих местах обувь будет давить и натирать.")
    elif loose_zones and not tight_zones:
        overall = "loose"
        overall_text = ("Колодка подойдёт, но свободна в зонах: " + ", ".join(loose_zones) +
                        " — обувь будет великовата, стопа хуже фиксируется.")
    elif worst == 2:
        overall = "ok"
        overall_text = "Подойдёт, но с минимальным запасом — комфортно для лёгкой/летней обуви."
    else:
        overall = "good"
        overall_text = "Хорошо подойдёт — стопа помещается в колодку с комфортным запасом по всей длине."

    images = _render_overlays(f, l, y, foot_len, last_len, protrusion)

    return {
        "overall": overall,
        "overall_text": overall_text,
        "overlap_pct": overlap_pct,
        "length": {
            "foot_mm": round(foot_len, 1),
            "last_mm": round(last_len, 1),
            "ease_mm": round(length_ease, 1),
            "verdict": len_verdict,
        },
        "girths": {
            "ball": _girth_pair(foot, last, "ball_girth_mm"),
            "instep": _girth_pair(foot, last, "instep_girth_mm"),
        },
        "zones": zones,
        "images": images,
    }


def _girth_pair(foot: dict, last: dict, key: str) -> dict | None:
    fv, lv = foot.get(key), last.get(key)
    if fv is None or lv is None:
        return None
    return {"foot_mm": round(fv, 1), "last_mm": round(lv, 1), "ease_mm": round(lv - fv, 1)}


# -- overlay rendering ------------------------------------------------------

def _png(fig: Figure) -> str:
    buf = io.BytesIO()
    FigureCanvasAgg(fig).print_png(buf)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _render_overlays(f: dict, l: dict, y: np.ndarray, foot_len: float,
                     last_len: float, protrusion: np.ndarray) -> dict:
    bad = np.nan_to_num(protrusion, nan=0.0) > PROTRUSION_MM

    # top view (footprint): last filled grey, foot outline blue, clashes red
    fig1 = Figure(figsize=(4.2, 6.8), dpi=140)
    ax1 = fig1.add_subplot(111)
    ok = ~np.isnan(l["medial"]) & ~np.isnan(l["lateral"])
    ax1.fill_betweenx(y[ok], l["lateral"][ok], l["medial"][ok], color="0.85", label="колодка")
    ax1.plot(f["medial"], y, "b-", lw=1.4, label="стопа")
    ax1.plot(f["lateral"], y, "b-", lw=1.4)
    ax1.plot(f["medial"][bad], y[bad], "r.", ms=5, zorder=5)
    ax1.plot(f["lateral"][bad], y[bad], "r.", ms=5, zorder=5)
    ax1.set_title("Стопа в колодке (сверху)", fontsize=9)
    ax1.set_xlabel("ширина, мм"); ax1.set_ylabel("длина от пятки, мм")
    ax1.set_aspect("equal"); ax1.legend(fontsize=7, loc="lower right")

    # side view: last profile grey, foot dorsal profile blue, clashes red
    fig2 = Figure(figsize=(7.0, 3.6), dpi=140)
    ax2 = fig2.add_subplot(111)
    okt = ~np.isnan(l["top"])
    ax2.fill_between(y[okt], 0, l["top"][okt], color="0.85", label="колодка")
    ax2.plot(y, f["top"], "b-", lw=1.4, label="стопа")
    ax2.plot(y[bad], f["top"][bad], "r.", ms=5, zorder=5)
    ax2.set_title("Стопа в колодке (сбоку)", fontsize=9)
    ax2.set_xlabel("длина от пятки, мм"); ax2.set_ylabel("высота, мм")
    ax2.set_aspect("equal"); ax2.legend(fontsize=7, loc="upper right")

    for fig in (fig1, fig2):
        fig.tight_layout()
    return {"top": _png(fig1), "side": _png(fig2)}
