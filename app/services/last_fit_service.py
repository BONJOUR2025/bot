"""Compare a foot scan against a shoe-last (колодка) scan and explain fit.

There's no single universal fitting-allowance standard — this uses two
published reference points, treated as reasonable defaults rather than a
certified spec:

- Length: ГОСТ 3927-88 ("Колодки обувные") sets a MINIMUM allowance of 5mm
  (summer/liner-less/moccasin-type footwear) or 10mm (most other footwear)
  of last length over foot length. Bespoke-shoemaking sources (3DShoemaker,
  PodoHub) put the typical average around 13mm, with up to ~17mm used for
  round-toe lasts.
- Ball girth: research on footwear fit (see PodoHub / ball-girth studies)
  found allowances under ~12mm at the ball girth were judged comfortable in
  the large majority of cases, with ~10mm cited elsewhere as typical
  metatarsal-joint width expansion; a last with less than a few mm of ease
  here risks pinching at the widest part of the forefoot.

Width (bounding-box) isn't used for the verdict — see scm_parser_service's
module docstring: it's a raw bounding box, not a validated anatomical
measurement, so it's surfaced as advisory info only.
"""
from __future__ import annotations

from dataclasses import dataclass

LENGTH_MIN_MM = 5.0
LENGTH_TIGHT_OK_MM = 8.0
LENGTH_IDEAL_MAX_MM = 13.0
LENGTH_LOOSE_OK_MM = 18.0

BALL_GIRTH_MIN_MM = 4.0
BALL_GIRTH_TIGHT_OK_MM = 6.0
BALL_GIRTH_IDEAL_MAX_MM = 12.0
BALL_GIRTH_LOOSE_OK_MM = 16.0


@dataclass
class MetricVerdict:
    metric: str
    label: str
    foot_mm: float
    last_mm: float
    delta_mm: float
    verdict: str  # "too_tight" | "tight_ok" | "ideal" | "loose_ok" | "too_loose"
    explanation: str


def _classify(delta: float, min_mm: float, tight_ok_mm: float, ideal_max_mm: float, loose_ok_mm: float,
              label: str) -> tuple[str, str]:
    if delta < min_mm:
        return "too_tight", (
            f"{label}: запас всего {delta:+.1f} мм — колодка теснее стопы или впритык, "
            f"минимально допустимый запас {min_mm:.0f} мм. Риск натирания/сдавливания."
        )
    if delta < tight_ok_mm:
        return "tight_ok", (
            f"{label}: запас {delta:+.1f} мм — на грани минимума, подойдёт для тонкого носка "
            f"или летней/бесподкладочной обуви, для закрытой обуви маловато."
        )
    if delta <= ideal_max_mm:
        return "ideal", f"{label}: запас {delta:+.1f} мм — в комфортном диапазоне."
    if delta <= loose_ok_mm:
        return "loose_ok", f"{label}: запас {delta:+.1f} мм — свободнее обычного, но не критично."
    return "too_loose", (
        f"{label}: запас {delta:+.1f} мм — заметно больше нормы, обувь на этой колодке "
        f"будет ощущаться велика в этом месте."
    )


def evaluate_fit(foot: dict, last: dict) -> dict:
    """foot/last: dicts with length_mm, width_mm, ball_girth_mm (ball_girth_mm may be None)."""
    metrics: list[MetricVerdict] = []

    length_delta = last["length_mm"] - foot["length_mm"]
    v, expl = _classify(length_delta, LENGTH_MIN_MM, LENGTH_TIGHT_OK_MM,
                         LENGTH_IDEAL_MAX_MM, LENGTH_LOOSE_OK_MM, "Длина")
    metrics.append(MetricVerdict("length", "Длина", foot["length_mm"], last["length_mm"],
                                  length_delta, v, expl))

    if foot.get("ball_girth_mm") is not None and last.get("ball_girth_mm") is not None:
        girth_delta = last["ball_girth_mm"] - foot["ball_girth_mm"]
        v, expl = _classify(girth_delta, BALL_GIRTH_MIN_MM, BALL_GIRTH_TIGHT_OK_MM,
                             BALL_GIRTH_IDEAL_MAX_MM, BALL_GIRTH_LOOSE_OK_MM, "Обхват пучков")
        metrics.append(MetricVerdict("ball_girth", "Обхват пучков", foot["ball_girth_mm"],
                                      last["ball_girth_mm"], girth_delta, v, expl))

    verdicts = {m.verdict for m in metrics}
    if "too_tight" in verdicts:
        overall = "not_fit"
        overall_text = "Не подойдёт: " + "; ".join(
            m.explanation for m in metrics if m.verdict == "too_tight"
        )
    elif "too_loose" in verdicts:
        overall = "loose"
        overall_text = "Подойдёт, но будет свободнее нужного: " + "; ".join(
            m.explanation for m in metrics if m.verdict == "too_loose"
        )
    elif verdicts <= {"ideal"}:
        overall = "good"
        overall_text = "Хорошо подойдёт по всем измеренным параметрам."
    else:
        overall = "ok"
        overall_text = "В целом подойдёт, но с минимальным запасом по некоторым параметрам."

    return {
        "overall": overall,
        "overall_text": overall_text,
        "metrics": [
            {
                "metric": m.metric,
                "label": m.label,
                "foot_mm": round(m.foot_mm, 1),
                "last_mm": round(m.last_mm, 1),
                "delta_mm": round(m.delta_mm, 1),
                "verdict": m.verdict,
                "explanation": m.explanation,
            }
            for m in metrics
        ],
        "width_advisory": {
            "foot_mm": foot.get("width_mm"),
            "last_mm": last.get("width_mm"),
            "note": "Ширина считается по крайним точкам облака (не откалиброванный анатомический "
                    "ориентир, в отличие от длины и обхвата пучков) — показана только для справки, "
                    "не входит в вердикт.",
        },
    }
