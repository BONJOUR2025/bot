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
they come from ГОСТ 3927-88 ("Колодки обувные", min 5-10 mm length allowance),
bespoke-lastmaking sources (3DShoemaker / PodoHub: ~13 mm typical length
allowance, 12-15 mm toe allowance more generally), Au's 2008 HKUST fit-
psychophysics thesis (allowance ≤6.4 mm at foot width / ≤12.1 mm at ball girth /
≤10.7 mm at waist girth was rated comfortable in >80% of trials — used here as
the upper edge of the "ideal" band, not a minimum), and Grau & Barisch-Fritz
2018 (practically-significant thresholds of ~2.5 mm girth / ~1 mm width, used
as the minimum ease below which a deficit counts as "tight" rather than noise).

Per-zone verdicts use a robust 10th/90th-percentile read of the ease values in
that zone rather than the raw min/max — a single noisy point in the point
cloud (this project has already hit scans with a handful of stray points, see
scm_parser_service) shouldn't flip a whole zone's verdict. This mirrors the
"P05 instead of d_min" principle from published foot/last distance-map studies
(Leng & Du 2006; Sambhav/Tandon/Dhande 2011).

The single most useful diagnostic from that literature: a last can have
ΔGirth ≥ 0 (looks fine on paper) while still being ΔHeight < 0 (too low) —
girth is redistributed into width instead of height, and the shoe still
presses on top of the foot. This service checks width-deficit and
height-deficit *separately* per zone and names whichever one is actually at
fault, instead of only reporting a combined "too tight".

Known limitation: a last has its own heel height and toe spring (the sole
curves up at the toe), so a technically correct comparison first re-poses the
flat-scanned foot into that posture before aligning it to the last (see
Leng & Du 2006; Chertenko et al. 2023). This service doesn't do that yet — both
the foot and the last profile are compared heel-anchored and flat. Revisit if
a real last scan shows that pose difference is large enough to matter.

A second, since-corrected limitation: equal ball girth (last == foot) is NOT
"ideal" — it used to be treated that way here. A last's girth is measured on
its *outer* surface; the finished shoe's *interior* girth is always smaller,
because the upper leather, lining, interlining and seams all sit between the
last's surface and the foot (a rough rule of thumb: interior girth loses
roughly 2π × combined-material-thickness — a 1-2mm leather+lining stack alone
costs ~6-13mm of girth). So `last girth == foot girth` means the *finished
shoe* is almost certainly tighter than the foot, not equal to it. The per-zone
bands below for ball girth follow the working table from that source directly:
< −5mm too tight (insufficient volume), −5..0mm tight/high risk, 0..+5mm
borderline (needs a fitting), +5..+10mm the actual comfortable band, > +10mm
excess/poor heel lock. Other zones (instep/waist/heel) don't have an
equally-sourced table; their bands are shifted by the same qualitative
principle (don't call raw equality "ideal") but are a rougher extrapolation —
worth tightening once we have fitting feedback for those zones specifically.

Width (bounding box) is used only for the visual overlay, not for the numeric
girth verdict — see scm_parser_service's module docstring on why the raw
bounding box isn't a calibrated measurement.

Three additions from a technical review of Oxford/Derby fit modelling
(digital_foot_last_fit_oxford_derby_technical.md, July 2026):

1. An explicit "uncertain" verdict. A girth difference smaller than the
   scanner/pipeline's own measurement noise (the review's own worked example:
   ball girth −0.6mm, well inside the ~±3-5mm noise band it cites for 3D-vs-
   manual girth comparisons) was previously classified as confidently "too
   tight" or "borderline" — a false precision. GIRTH_UNCERTAINTY_MM gates
   this: a girth-only classification within that band of a threshold reports
   "uncertain, needs a fitting" instead of a confident verdict. This does NOT
   apply to width/height protrusion — those come from directly overlaying the
   two shapes, not from subtracting two independently-noisy scalars, so they
   keep their existing (already fairly tight) PROTRUSION_MM cutoff.
2. Ball-line position check (`ball_line_mm`, §14.3 in the review). Two lasts
   can have the *same cross-sectional shape* at the ball yet crease the shoe
   in the wrong place lengthwise if their MT/MF landmark sits at a different
   distance from the heel than the foot's own joints — the fold then lands on
   bone, not the joint. Flagged past BALL_LINE_WARN_MM, called out as a hard
   failure past BALL_LINE_HARD_FAIL_MM.
3. Explicit hard-fail reasons as a layer above the usual zone scoring. A
   protrusion beyond HARD_FAIL_PROTRUSION_MM (the review's own suggested
   6mm) is reported as a named, non-negotiable failure reason rather than
   just tipping a zone to "too_tight" — the point being that a bad reason
   shouldn't read as just one more zone that happened to score low, and
   can't be averaged away by good scores elsewhere.

A fourth addition, from a follow-up review specifically on detecting
excessively loose lasts (izlishne_svobodnaya_kolodka_3d_fit_technical.md,
July 2026): excess width/height is now caught geometrically, not just via
girth. Girth is a 1D summary of a 2D cross-section, so a last can be
excessively wide or tall in one zone while its total girth still looks
unremarkable (the width gain and height gain of the *foot* balance out in
the girth sum even though the *last* doesn't match that split). This mirrors
the existing width/height *tightness* check (direct shape overlay, no
measurement-noise uncertainty gate) rather than the girth-based looseness
check — see ZONE_WIDTH_LOOSE_MM / ZONE_HEIGHT_LOOSE_MM.
"""
from __future__ import annotations

import base64
import io

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

# -- allowances / thresholds (mm) ------------------------------------------

LENGTH_MIN = 5.0        # below this the toe has nowhere to go (ГОСТ 3927-88 floor)
LENGTH_TIGHT = 8.0
LENGTH_IDEAL_MAX = 15.0  # ГОСТ/bespoke toe allowance upper edge (12-15 mm)
LENGTH_LOOSE = 22.0

# Girth ease (last − foot) bands, per zone. Below TOO_TIGHT = tight/high risk
# — note this includes 0 (raw last==foot girth is NOT a safe margin: the
# finished shoe's interior is smaller than the last's outer surface once
# upper + lining are added). TOO_TIGHT..IDEAL_MIN = borderline, needs a
# fitting. IDEAL_MIN..IDEAL_MAX = the actual comfortable band. Above
# IDEAL_MAX = excess volume / poor lock. "ball" is sourced directly (see
# module docstring); other zones are shifted by the same principle but not
# independently validated.
ZONE_GIRTH_TOO_TIGHT = {"ball": 0.0, "instep": 0.0, "waist": -1.0, "heel": -1.0}
ZONE_GIRTH_IDEAL_MIN = {"ball": 5.0, "instep": 5.0, "waist": 4.0, "heel": 3.0}
ZONE_GIRTH_IDEAL_MAX = {"ball": 10.0, "instep": 11.0, "waist": 9.0, "heel": 7.0}

# A foot edge poking out this far (mm) past the last outline is a hard clash,
# not noise. There's no calibrated u_model for this scanner/pipeline yet (see
# module docstring §5.4 in the source material) — 2 mm is a placeholder
# in line with the ~1-2 mm combined-error examples in that literature.
PROTRUSION_MM = 2.0

# zones as fractions of FOOT length, heel = 0
ZONES = [
    ("heel", 0.00, 0.25, "Пятка"),
    ("waist", 0.25, 0.42, "Свод / талия"),
    ("instep", 0.42, 0.60, "Подъём"),
    ("ball", 0.60, 0.78, "Пучки (широкая часть)"),
    ("toe", 0.78, 1.00, "Носок (пальцы)"),
]

# Whether a height deficit (foot taller than last) counts as "presses down" in
# a given zone. In heel/waist it does NOT: our foot scans include the ankle
# and part of the lower leg (up to ~125 mm — confirmed on a real last test,
# where a foot scan showed z up to 127 mm at 5-30% of length while the last
# itself tops out under 100 mm total). A last only models the shoe's own
# topline height there, and most closed shoes (anything but tall boots) don't
# enclose the ankle at all — the foot simply rises above an open collar, which
# isn't pressure. In instep/ball the upper genuinely wraps over the top of the
# foot, so a height deficit there is real and meaningful.
ZONE_HEIGHT_MATTERS = {"heel": False, "waist": False, "instep": True, "ball": True}

# Same contamination, different measurement: "girth" per section is the
# perimeter of the full vertical (x, z) slice on purpose (a tape measured
# girth legitimately wraps around whatever height variation exists — see
# FOOTPRINT_HEIGHT_MM's docstring in scm_parser_service for why width is
# capped but girth isn't). But in heel/waist that same full-height slice
# includes the ankle/calf column, so the foot's "girth" there is essentially
# a lower-leg circumference (confirmed on a real last test: girth ease of
# roughly −100 to −110 mm, which is not a real shoe-fit deficit, just a
# last having no leg above it at all). Girth-based tight/loose verdicts are
# only meaningful where the last and the foot are actually comparable —
# instep and ball. Heel/waist still get a verdict from width protrusion.
ZONE_GIRTH_MATTERS = {"heel": False, "waist": False, "instep": True, "ball": True}

# Instep is reported at several sections (40-60% of length), not just 50% —
# published systems disagree on where exactly "the" instep section is (IEEE SA
# 2021 terminology review lists 40/45/50/55%), so the worst section in this
# range is used for the verdict instead of a single arbitrary cut.
INSTEP_SECTION_FRACS = (0.40, 0.45, 0.50, 0.55, 0.60)

# A girth-only classification within this many mm of a tight/loose boundary
# is reported as "uncertain" rather than a confident verdict — smaller than
# the ~3-5mm noise band cited for 3D-vs-manual girth comparisons.
GIRTH_UNCERTAINTY_MM = 4.0

# Excess width/height (last roomier than foot on BOTH the medial and lateral
# side at once, or taller on top) reported as "too loose" directly from the
# shape overlay — the mirror image of the width/height *tightness* check
# above. Until now only girth caught looseness, which misses the case a
# review of Oxford/Derby fit flagged explicitly: a last can be excessively
# wide/tall in one zone while its total girth still looks unremarkable,
# because girth is a 1D summary of a 2D shape. Heel is intentionally
# stricter — slack there is the single biggest driver of heel slip, per that
# same review ("для пятки пороги должны быть строже").
ZONE_WIDTH_LOOSE_MM = {"heel": 4.0, "waist": 6.0, "instep": 6.0, "ball": 6.0}
# Only in zones where height is even meaningful (see ZONE_HEIGHT_MATTERS) —
# heel/waist height is ankle/calf, not a real dorsal-volume signal either way.
ZONE_HEIGHT_LOOSE_MM = {"instep": 6.0, "ball": 6.0}

# How far the ball line (MT/MF landmark position along the length) can be
# off between foot and last before the crease is landing somewhere other
# than the foot's own joints. WARN = worth a manual look; HARD_FAIL = the
# fold is unambiguously in the wrong place.
BALL_LINE_WARN_MM = 4.0
BALL_LINE_HARD_FAIL_MM = 10.0

# A protrusion (width or height) beyond this is reported as an explicit,
# named hard-fail reason rather than just another zone that scored "tight".
HARD_FAIL_PROTRUSION_MM = 6.0


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


# Split by cause (narrow vs low) rather than one generic "tight" sentence per
# zone — a last can have plenty of girth but still press from above if that
# girth is redistributed into width instead of height (ΔG≥0, ΔW>0, ΔH<0 is a
# well-documented trap: girth alone says "fits", but the foot's top surface
# still pokes through the last).
_ZONE_TIGHT_WIDTH = {
    "heel": "Пятка колодки уже пятки стопы по бокам — задник будет сдавливать и "
            "натирать пятку с боков, возможны мозоли.",
    "waist": "В своде колодка узкая по бокам — обувь будет сжимать стопу по "
             "центру с боков.",
    "instep": "Подъём колодки узкий по бокам — обувь будет сдавливать стопу с "
              "боков в районе подъёма.",
    "ball": "В пучках (самое широкое место) колодка уже стопы по бокам — будет "
            "сдавливать косточки у основания большого пальца и мизинца, "
            "натирать, вызывать онемение пальцев; частая причина «жмёт в носке».",
}
_ZONE_TIGHT_HEIGHT = {
    "heel": "Колодка ниже пятки стопы — задник будет давить на пятку сверху.",
    "waist": "Свод колодки ниже свода стопы — будет давить сверху по центру "
             "стопы, ощущение сжатия, особенно у людей с высоким сводом.",
    "instep": "Подъём колодки ниже подъёма стопы — верх обуви и шнуровка будут "
              "врезаться в подъём сверху, давить на сухожилия и сосуды, нога "
              "быстро устаёт и немеет. Часто это не видно по обхвату: колодка "
              "может быть даже шире стопы, но при этом ниже — обхват "
              "совпадает или больше, а давит всё равно сверху.",
    "ball": "Колодка ниже стопы в пучках — верх обуви будет давить сверху на "
            "плюсну и пальцы, даже если по обхвату колодка не уже.",
}
# Mirror image of the two dicts above: excess room on BOTH sides at once
# (not just one side, which would be a misalignment, not real width slack) or
# excess height. Girth alone can hide this — a wide-but-not-tall zone and a
# not-wide-but-tall zone can report the same total girth.
_ZONE_LOOSE_WIDTH = {
    "heel": "Пятка колодки заметно шире пятки стопы с обеих сторон — пятка не "
            "фиксируется, будет гулять из стороны в сторону и быстрее натирать; "
            "самая частая геометрическая причина, когда «пятка выскакивает».",
    "waist": "В своде много места по бокам с обеих сторон — стопа слабо "
             "зафиксирована по центру, может смещаться вбок при ходьбе.",
    "instep": "В подъёме много места по бокам с обеих сторон — стопа может "
              "смещаться вбок, и не факт что шнуровка вообще способна выбрать "
              "такой запас.",
    "ball": "В пучках колодка заметно шире стопы с обеих сторон — стопа гуляет "
            "вбок при перекате, снижается устойчивость шага.",
}
_ZONE_LOOSE_HEIGHT = {
    "instep": "Над подъёмом стопы много лишнего места сверху — верх и шнуровка "
              "не дотягиваются, чтобы плотно прижать стопу; шнуровка быстро "
              "исчерпает запас стягивания, а стопа продолжит двигаться внутри.",
    "ball": "Над пучками много лишнего места сверху — обувь ощущается пустой в "
            "этом месте, могут образовываться глубокие заломы союзки.",
}
# Girth ease is 0..+borderline mm: raw last-vs-foot girth looks equal or only
# slightly bigger. Not a fault, but not a confirmed margin either — the
# finished shoe's interior will be smaller than the last (upper + lining sit
# between them), so this needs an actual fitting rather than a "yes" from the
# numbers alone.
_ZONE_BORDERLINE = {
    "heel": "Обхват пятки у колодки примерно равен стопе — прямого запаса нет. "
            "С учётом материалов задника посадка может оказаться плотной, "
            "нужна примерка.",
    "waist": "Обхват в своде примерно равен стопе — запаса по факту может не "
             "остаться после материалов верха, нужна примерка.",
    "instep": "Обхват подъёма примерно равен стопе — это не гарантия запаса: "
              "верх и подкладка отнимут часть объёма, посадка может оказаться "
              "плотной, особенно к вечеру. Нужна примерка.",
    "ball": "Обхват пучков колодки примерно равен обхвату стопы — это "
            "пограничный случай, а не подтверждённый запас: между стопой и "
            "колодкой в готовой обуви будут материалы верха и подкладки, "
            "отнимающие часть объёма. Посадка вероятно плотная, нужна примерка.",
}
def _uncertain_text(label: str, diff_mm: float) -> str:
    return (
        f"Разница по обхвату в зоне «{label}» ({diff_mm:+.1f} мм) меньше ожидаемой точности "
        f"измерения (~±{GIRTH_UNCERTAINTY_MM:.0f} мм) — по этому параметру нельзя уверенно "
        f"сказать, жмёт колодка или нет. Нужна примерка."
    )


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

    # excess (mirror of protrusion): last roomier than the foot on BOTH sides
    # at once — one-sided slack alone is a lengthwise/lateral misalignment,
    # not genuine width excess, so this takes the smaller of the two sides.
    excess_width = np.fmax(np.fmin(medial_ease, lateral_ease), 0.0)
    excess_height = np.fmax(top_ease, 0.0)

    inside = np.nan_to_num(protrusion, nan=0.0) <= PROTRUSION_MM
    valid = ~np.isnan(protrusion)
    overlap_pct = round(100.0 * inside[valid].sum() / max(valid.sum(), 1), 1)

    length_ease = last_len - foot_len
    len_verdict, len_text = _length_consequence(length_ease)

    # Ball and instep already have a precise, landmark-based girth (the
    # oblique MT/MF cut for ball; the fixed I50 section for instep) — shown
    # to the user as "Обхват пучков"/"Обхват подъёма". The per-section
    # profile's own "girth" curve, used below for the other zones, is a much
    # cruder plain-perpendicular estimate averaged over a whole zone, and the
    # two can disagree (one call it borderline, the other loose) — exactly
    # the confusing mismatch a user spotted between the summary numbers and
    # the zone verdict. Zone verdicts for these two zones use the precise
    # scalar instead of recomputing their own from the profile.
    precise_girth_ease = {}
    for gkey in ("ball", "instep"):
        fg, lg = foot.get(f"{gkey}_girth_mm"), last.get(f"{gkey}_girth_mm")
        if fg is not None and lg is not None:
            precise_girth_ease[gkey] = lg - fg

    zones = []
    frac = y / foot_len
    for key, lo, hi, label in ZONES:
        sel = (frac >= lo) & (frac < hi) & valid
        if not sel.any():
            continue
        if key in precise_girth_ease:
            gmin = gmean = precise_girth_ease[key]
        else:
            zg = girth_ease[sel]
            # Robust "worst typical" reading (10th/90th percentile) instead of
            # a bare min/max — a single noisy point in the scan shouldn't
            # decide a whole zone's verdict (see module docstring).
            gmin = float(np.nanpercentile(zg, 10)) if np.isfinite(zg).any() else None
            gmean = float(np.nanmean(zg)) if np.isfinite(zg).any() else None
        worst_protr = float(np.nanpercentile(protrusion[sel], 90))
        worst_protr_w = float(np.nanpercentile(protr_width[sel], 90))
        worst_protr_h = float(np.nanpercentile(protr_height[sel], 90))
        # 10th percentile: "even the tightest point in this zone still has
        # this much room" — the same robust-worst-case read used elsewhere,
        # just from the loose end instead of the tight end.
        least_excess_w = float(np.nanpercentile(excess_width[sel], 10))
        least_excess_h = float(np.nanpercentile(excess_height[sel], 10))

        if key == "toe":
            verdict, text = len_verdict, len_text  # toe room ~ length verdict
        else:
            tight_thr = ZONE_GIRTH_TOO_TIGHT[key]
            ideal_min = ZONE_GIRTH_IDEAL_MIN[key]
            ideal_max = ZONE_GIRTH_IDEAL_MAX[key]
            girth_matters = ZONE_GIRTH_MATTERS[key]
            tight_by_girth = girth_matters and gmin is not None and gmin < tight_thr
            borderline_by_girth = girth_matters and gmin is not None and tight_thr <= gmin < ideal_min
            loose_by_girth = girth_matters and gmean is not None and gmean > ideal_max
            tight_by_width = worst_protr_w > PROTRUSION_MM
            tight_by_height = ZONE_HEIGHT_MATTERS[key] and worst_protr_h > PROTRUSION_MM
            loose_width_thr = ZONE_WIDTH_LOOSE_MM.get(key)
            loose_height_thr = ZONE_HEIGHT_LOOSE_MM.get(key)
            loose_by_width = loose_width_thr is not None and least_excess_w > loose_width_thr
            loose_by_height = (
                ZONE_HEIGHT_MATTERS[key] and loose_height_thr is not None
                and least_excess_h > loose_height_thr
            )

            if tight_by_width or tight_by_height:
                verdict = "too_tight"
                parts = []
                if tight_by_height:
                    parts.append(_ZONE_TIGHT_HEIGHT[key])
                if tight_by_width:
                    parts.append(_ZONE_TIGHT_WIDTH[key])
                text = " ".join(parts)
            elif loose_by_width or loose_by_height:
                # Same direct shape-overlay logic as tight_by_width/height —
                # trusted outright, no uncertainty gate (unlike girth).
                verdict = "too_loose"
                parts = []
                if loose_by_height:
                    parts.append(_ZONE_LOOSE_HEIGHT[key])
                if loose_by_width:
                    parts.append(_ZONE_LOOSE_WIDTH[key])
                text = " ".join(parts)
            elif tight_by_girth:
                # A geometric (width/height) clash is a direct shape overlay,
                # not a subtraction of two noisy scalars — trust it outright.
                # A tight verdict from girth ALONE is different: it's the
                # difference of two independently-measured numbers, so a
                # small deficit can be measurement noise rather than a real
                # conflict. Only call it confidently "tight" once the deficit
                # clears the expected noise band.
                if (tight_thr - gmin) < GIRTH_UNCERTAINTY_MM:
                    verdict, text = "uncertain", _uncertain_text(label, gmin - tight_thr)
                else:
                    verdict, text = "too_tight", _ZONE_BORDERLINE[key]
            elif borderline_by_girth:
                verdict, text = "tight_ok", _ZONE_BORDERLINE[key]
            elif loose_by_girth:
                if (gmean - ideal_max) < GIRTH_UNCERTAINTY_MM:
                    verdict, text = "uncertain", _uncertain_text(label, gmean - ideal_max)
                else:
                    verdict, text = "too_loose", _ZONE_LOOSE[key]
            else:
                verdict, text = "ideal", "Посадка в норме — колодка повторяет стопу с комфортным запасом."
        girth_relevant = key != "toe" and ZONE_GIRTH_MATTERS.get(key, True)
        zones.append({
            "zone": key,
            "label": label,
            "verdict": verdict,
            "explanation": text,
            # Null, not just unused, where girth is contaminated by the
            # ankle/calf column and isn't part of the verdict (see
            # ZONE_GIRTH_MATTERS) — a raw number here would look like a
            # real ~100mm+ deficit and isn't one.
            "girth_ease_min_mm": round(gmin, 1) if (gmin is not None and girth_relevant) else None,
            "girth_ease_mean_mm": round(gmean, 1) if (gmean is not None and girth_relevant) else None,
            "max_protrusion_mm": round(worst_protr, 1),
            "max_protrusion_width_mm": round(worst_protr_w, 1),
            "max_protrusion_height_mm": round(worst_protr_h, 1),
            "excess_width_mm": round(least_excess_w, 1),
            "excess_height_mm": round(least_excess_h, 1),
        })

    # I40-I60: sample the instep at several candidate sections rather than a
    # single fixed 50% cut — published systems don't agree on where "the"
    # instep section is (40/45/50/55%), so report height/girth ease at each
    # and let the worst one drive attention, not just I50.
    instep_sections = []
    for pct in INSTEP_SECTION_FRACS:
        yc = pct * foot_len
        idx = int(np.argmin(np.abs(y - yc)))
        if not valid[idx]:
            continue
        instep_sections.append({
            "pct": int(round(pct * 100)),
            "height_ease_mm": round(float(top_ease[idx]), 1),
            "girth_ease_mm": round(float(girth_ease[idx]), 1),
        })

    # Ball-line position: does the last's flex-line landmark sit at the same
    # distance from the heel as the foot's own MTH1/5 joints? A last can pass
    # every cross-sectional check above and still crease over a bone.
    ball_line = None
    fbl, lbl = foot.get("ball_line_mm"), last.get("ball_line_mm")
    if fbl is not None and lbl is not None:
        bl_diff = lbl - fbl
        ball_line = {
            "foot_mm": round(fbl, 1),
            "last_mm": round(lbl, 1),
            "diff_mm": round(bl_diff, 1),
            "flagged": abs(bl_diff) > BALL_LINE_WARN_MM,
        }

    # Hard-fail reasons: named, non-negotiable problems that shouldn't be
    # averaged away by decent scores in other zones (see module docstring).
    # Must use the same *verdict-relevant* protrusion the zone loop used —
    # not the raw max_protrusion_mm field, which still includes the height
    # component even in heel/waist where ZONE_HEIGHT_MATTERS says that's
    # ankle/calf contamination, not a real conflict (a bug caught by exactly
    # that: heel/waist showed 35-44mm "conflicts" here before this fix).
    hard_fail_reasons = []
    for z in zones:
        if z["zone"] == "toe":
            continue
        relevant_protr = z["max_protrusion_width_mm"]
        if ZONE_HEIGHT_MATTERS.get(z["zone"], True):
            relevant_protr = max(relevant_protr, z["max_protrusion_height_mm"])
        if relevant_protr > HARD_FAIL_PROTRUSION_MM:
            hard_fail_reasons.append(
                f"{z['label']}: локальный конфликт {relevant_protr:.1f} мм — "
                "прямое геометрическое несоответствие, а не пограничный случай"
            )
    if length_ease < 0:
        hard_fail_reasons.append(f"длина: колодка короче стопы на {abs(length_ease):.1f} мм")
    if ball_line and abs(ball_line["diff_mm"]) > BALL_LINE_HARD_FAIL_MM:
        hard_fail_reasons.append(
            f"линия сгиба пучков смещена на {ball_line['diff_mm']:+.1f} мм — сгиб обуви "
            "попадёт на кость, а не на сустав"
        )

    ranks = {"too_tight": 3, "tight_ok": 2, "too_loose": 1, "loose_ok": 1, "uncertain": 1, "ideal": 0}
    worst = max((ranks.get(z["verdict"], 0) for z in zones), default=0)
    tight_zones = [z["label"] for z in zones if z["verdict"] == "too_tight"]
    loose_zones = [z["label"] for z in zones if z["verdict"] == "too_loose"]
    uncertain_zones = [z["label"] for z in zones if z["verdict"] == "uncertain"]

    if hard_fail_reasons:
        overall = "not_fit"
        overall_text = ("Колодка не подойдёт — жёсткий критерий отказа: " + "; ".join(hard_fail_reasons) +
                        ". Это не оценка по сумме баллов — такое несоответствие не компенсируется "
                        "хорошими показателями в других зонах.")
    elif worst >= 3:
        overall = "not_fit"
        overall_text = ("Колодка не подойдёт: тесно в зонах — " + ", ".join(tight_zones) +
                        ". В этих местах обувь будет давить и натирать.")
    elif loose_zones and not tight_zones:
        overall = "loose"
        overall_text = ("Колодка подойдёт, но свободна в зонах: " + ", ".join(loose_zones) +
                        " — обувь будет великовата, стопа хуже фиксируется.")
    elif worst == 2:
        overall = "ok"
        if uncertain_zones and not tight_zones:
            overall = "uncertain"
            overall_text = ("По зонам (" + ", ".join(uncertain_zones) + ") разница меньше точности "
                            "измерения — нельзя однозначно сказать, подойдёт колодка или нет. "
                            "Нужна примерка.")
        else:
            overall_text = "Подойдёт, но с минимальным запасом — комфортно для лёгкой/летней обуви."
    else:
        overall = "good"
        overall_text = "Хорошо подойдёт — стопа помещается в колодку с комфортным запасом по всей длине."

    if ball_line and ball_line["flagged"] and overall in ("good", "ok"):
        overall_text += (
            f" Отдельно: линия сгиба пучков смещена на {ball_line['diff_mm']:+.1f} мм "
            "относительно суставов стопы — стоит проверить при примерке, куда придётся залом."
        )

    images = _render_overlays(f, l, y, foot_len, last_len, protrusion)

    return {
        "overall": overall,
        "overall_text": overall_text,
        "overlap_pct": overlap_pct,
        "hard_fail_reasons": hard_fail_reasons,
        "ball_line": ball_line,
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
        "instep_sections": instep_sections,
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
