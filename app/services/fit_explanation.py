"""Human-readable explanation of a fit result -- what is wrong, by how much,
and what the wearer will actually feel.

Written against §21 of audit_nedochety_tekushchey_sistemy_podbora_kolodki.md,
which objects to verdicts that assert a consequence as fact ("пятка будет
выскакивать" from one width number). Every finding here is split into the four
things that must not be conflated:

    факт       -- the measured geometry, with its number and units
    эффект     -- what that plausibly means for the wearer, phrased as a
                  likelihood, never as a certainty
    уверенность-- how much the measurement is worth, given §18's budget
    проверить  -- what a human should confirm before acting on it

Findings are ordered by severity so the reader meets the decisive problem
first, instead of a wall of equally-weighted paragraphs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CRITICAL = "critical"
WARNING = "warning"
GOOD = "good"
NEUTRAL = "neutral"

_SEVERITY_ORDER = {CRITICAL: 0, WARNING: 1, NEUTRAL: 2, GOOD: 3}

ZONE_LABEL = {
    "posterior_heel": "Задник пятки",
    "heel": "Пятка",
    "waist": "Геленок (свод)",
    "instep": "Подъём",
    "ball": "Пучки",
    "toes": "Пальцы",
    "toe_tip": "Кончики пальцев",
}

# What tightness in each zone actually does to the wearer. Phrased as
# likelihood: geometry alone cannot promise a sensation (§21).
_TIGHT_EFFECT = {
    "posterior_heel": "Задник давит на ахилл — вероятны натирание и намин в первые часы.",
    "heel": "Пяточная часть узка — возможны давление по бокам пятки и намин.",
    "waist": "Тесно в своде — обувь будет ощущаться жёсткой при перекате.",
    "instep": "Давление сверху на подъём — возможны онемение и следы от берцев.",
    "ball": "Сдавливание в самом широком месте стопы — самая частая причина боли, натоптышей и деформации сустава при постоянном ношении.",
    "toes": "Пальцам тесно — вероятны натирание боковых поверхностей и вросшие ногти.",
    "toe_tip": "Пальцы упираются в носок — при ходьбе под уклон ноготь будет биться о верх.",
}

_LOOSE_EFFECT = {
    "posterior_heel": "За пяткой пусто — вероятно проскальзывание пятки при шаге.",
    "heel": "Пятка сидит свободно — обувь может спадать, нужен более плотный задник.",
    "waist": "Свод не поддержан — стопа будет гулять внутри.",
    "instep": "Много места сверху — частично убирается шнуровкой, но при большом запасе появятся заломы верха.",
    "ball": "Стопа болтается в пучках — обувь будет ощущаться великоватой.",
    "toes": "Свободно в пальцах — само по себе не мешает, если пятка держится.",
    "toe_tip": "Большой запас перед пальцами — обувь может выглядеть и ощущаться длиннее нужного.",
}

_DIRECTION_LABEL = {
    "medial": "с внутренней стороны",
    "lateral": "с внешней стороны",
    "dorsal": "сверху",
    "plantar": "снизу",
}


@dataclass
class Finding:
    severity: str
    zone: str
    title: str
    fact: str
    effect: str
    confidence: float
    check: str | None = None

    def as_dict(self) -> dict:
        return {
            "severity": self.severity,
            "zone": self.zone,
            "title": self.title,
            "fact": self.fact,
            "effect": self.effect,
            "confidence": round(self.confidence, 2),
            "check": self.check,
        }


@dataclass
class Explanation:
    headline: str
    summary: str
    findings: list[Finding] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "headline": self.headline,
            "summary": self.summary,
            "findings": [f.as_dict() for f in self.findings],
            "caveats": list(self.caveats),
        }


def _worst_direction(directional: dict) -> tuple[str | None, float | None]:
    """Which way the zone is tightest, and by how much."""
    negatives = {k: v for k, v in directional.items() if v is not None and v < 0}
    if not negatives:
        return None, None
    key = min(negatives, key=lambda k: negatives[k])
    return key, negatives[key]


def _zone_finding(zone: dict, sigma: float) -> Finding:
    name = zone["name"]
    label = ZONE_LABEL.get(name, name)
    gap = zone["signed_gap_mm"]
    median = gap["median"]
    compression = zone["required_compression_mm"]["p95"]
    area = zone["conflict_area_mm2"]
    classification = zone["classification"]
    confidence = zone["confidence"]
    direction, dir_mm = _worst_direction(zone.get("directional_mm") or {})
    where = f" {_DIRECTION_LABEL[direction]}" if direction else ""

    if classification == "LOCAL_TIGHTNESS":
        # Severity by how far past the noise floor it is, and how much of the
        # surface is involved -- a deep pinprick and a broad press are not the
        # same problem (§11 of the audit).
        severe = compression >= 3.0 * sigma or area >= 800.0
        return Finding(
            severity=CRITICAL if severe else WARNING,
            zone=name,
            title=f"{label}: тесно на {abs(median):.0f} мм",
            fact=(f"Стопа выходит за полость обуви{where} — в среднем на {abs(median):.0f} мм, "
                  f"в худших точках до {compression:.0f} мм, на площади около {area:.0f} мм²."),
            effect=_TIGHT_EFFECT.get(name, "Возможно давление в этой зоне."),
            confidence=confidence,
            check=("Проверить примеркой: где именно давит и уходит ли ощущение "
                   "после разноски" if not severe else
                   "Требуется другая полнота или расширение колодки в этой зоне — "
                   "разноской такой объём не берётся"),
        )

    if classification == "NOT_SEATED":
        seating = zone.get("seating_gap_mm") or 0.0
        return Finding(
            severity=NEUTRAL,
            zone=name,
            title=f"{label}: стопа не лежит на следе ({abs(seating):.0f} мм)",
            fact=(f"След колодки здесь поднят примерно на {abs(seating):.0f} мм "
                  f"относительно плоско отсканированной стопы — это носочный подъём "
                  f"колодки, а не нехватка места."),
            effect=("В обуви стопа ляжет на этот подъём, а не продавит его. "
                    "Оценить тесноту в этой зоне по плоскому скану нельзя."),
            confidence=confidence,
            check="Для точной оценки нужен скан стопы на опоре, повторяющей подъём колодки",
        )

    if classification == "LOCAL_LOOSENESS":
        return Finding(
            severity=WARNING,
            zone=name,
            title=f"{label}: свободно на {median:.0f} мм",
            fact=f"Между стопой и полостью обуви около {median:.0f} мм свободного места.",
            effect=_LOOSE_EFFECT.get(name, "Возможна недостаточная фиксация."),
            confidence=confidence,
            check="Проверить, убирается ли объём шнуровкой и держится ли пятка при шаге",
        )

    if classification == "WITHIN_UNCERTAINTY":
        return Finding(
            severity=GOOD,
            zone=name,
            title=f"{label}: посадка в пределах точности измерения",
            fact=(f"Расхождение {median:+.0f} мм меньше суммарной погрешности "
                  f"±{sigma:.1f} мм, поэтому не считается ни теснотой, ни свободой."),
            effect="Отклонений, которые можно было бы уверенно назвать проблемой, здесь нет.",
            confidence=confidence,
        )

    return Finding(
        severity=GOOD, zone=name,
        title=f"{label}: нормально ({median:+.0f} мм)",
        fact=f"Запас {median:+.0f} мм — в рабочем диапазоне.",
        effect="Зона не требует вмешательства.",
        confidence=confidence,
    )


_HEADLINE = {
    "FIT_GOOD": "Колодка подходит",
    "FIT_LOCAL_TIGHTNESS": "Подходит с оговоркой: локальная теснота",
    "FIT_LOCAL_LOOSENESS": "Подходит с оговоркой: местами свободно",
    "FIT_REQUIRES_LAST_MODIFICATION": "Колодка не подходит без переделки",
    "FIT_INDETERMINATE": "Оценить не удалось",
}


def explain(report: dict) -> Explanation:
    """Turn a `fit_pipeline.analyze_fit` report into ordered, plain-language
    findings."""
    clearance = report.get("clearance") or {}
    zones = clearance.get("zones") or []
    sigma = (clearance.get("uncertainty") or {}).get("total_sigma_mm") or 1.0
    fit_class = report.get("fit_class", "FIT_INDETERMINATE")

    findings = sorted(
        (_zone_finding(z, sigma) for z in zones),
        key=lambda f: (_SEVERITY_ORDER[f.severity], -abs(f.confidence)),
    )

    tight = [f for f in findings if f.severity in (CRITICAL, WARNING) and "тесно" in f.title]
    loose = [f for f in findings if "свободно" in f.title]
    ok_count = sum(1 for f in findings if f.severity == GOOD)

    if fit_class == "FIT_REQUIRES_LAST_MODIFICATION":
        summary = (f"Теснота не локальная, а по большей части стопы "
                   f"({len(tight)} зон из {len(findings)}). Это не лечится разноской "
                   f"или шнуровкой — нужна другая полнота либо переделка колодки.")
    elif tight:
        worst = tight[0]
        summary = (f"Главная проблема — {ZONE_LABEL.get(worst.zone, worst.zone).lower()}. "
                   f"Остальные {ok_count} зон сидят нормально.")
    elif loose:
        summary = (f"Тесноты нет; есть запас в {len(loose)} зонах — "
                   f"вопрос фиксации, а не давления.")
    else:
        summary = f"Все {len(findings)} зон в пределах нормы."

    caveats = list(report.get("limitations") or [])
    caveats.insert(0, f"Суммарная погрешность измерения ±{sigma:.1f} мм — "
                      f"расхождения меньше этого не интерпретируются.")

    return Explanation(
        headline=_HEADLINE.get(fit_class, fit_class),
        summary=summary,
        findings=findings,
        caveats=caveats,
    )
