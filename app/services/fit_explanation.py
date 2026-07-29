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

from app.services.fit_size_match import LENGTH_ALLOWANCE_ACCEPTABLE

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

        # fit_clearance flags a zone on its *worst direction*, which can be
        # negative while the zone's median gap is positive or near zero: a
        # local press on one side of an otherwise roomy zone. Reporting
        # abs(median) then printed the wrong number entirely -- on a real pair
        # it read "задник пятки: тесно на 0 мм" for a 3.2mm medial press, and
        # elsewhere it turned +6mm of room into "тесно на 6 мм", the exact
        # inversion a wearer contradicted after trying the last on. The
        # headline number is the squeeze the classifier actually acted on.
        squeeze = abs(dir_mm) if dir_mm is not None else abs(min(median, 0.0))
        roomy = median > sigma
        return Finding(
            severity=CRITICAL if severe else WARNING,
            zone=name,
            title=f"{label}: тесно{where} на {squeeze:.0f} мм",
            fact=((f"Стопа упирается в полость обуви{where} на {squeeze:.0f} мм, "
                   f"хотя в среднем по зоне остаётся {median:.0f} мм свободного места — "
                   f"это местный упор с одной стороны, а не теснота всей зоны. "
                   f"В худших точках до {compression:.0f} мм, площадь около {area:.0f} мм².")
                  if roomy else
                  (f"Стопа выходит за полость обуви{where} — на {squeeze:.0f} мм, "
                   f"в худших точках до {compression:.0f} мм, на площади около {area:.0f} мм².")),
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
    "FIT_STRUCTURALLY_INCOMPATIBLE": "Не тот размер колодки",
    "FIT_REQUIRES_DIFFERENT_FULLNESS": "Размер верный — нужна другая полнота",
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

    # A size mismatch is the cause; the zone findings are its symptoms. It goes
    # first and says so, otherwise the reader meets six "independent" tightness
    # zones and never learns that a shorter last would remove all of them.
    sm = report.get("size_match") or {}
    if sm.get("gate_triggered"):
        parts = []
        if sm.get("length_allowance_mm") is not None:
            parts.append(f"припуск по длине {sm['length_allowance_mm']:.0f} мм "
                         f"при норме 10–15")
        if sm.get("ball_offset_mm") is not None:
            parts.append(f"пучки стопы и колодки расходятся на "
                         f"{abs(sm['ball_offset_mm']):.0f} мм ({abs(sm.get('ball_offset_pct') or 0):.1f}% длины)")
        findings.insert(0, Finding(
            severity=CRITICAL, zone="size",
            title="Колодка не того размера для этой стопы",
            fact="; ".join(parts) + "." if parts else "Соразмерность нарушена.",
            effect=("Самая широкая часть стопы попадает не в самое широкое место колодки, "
                    "а линия сгиба обуви не совпадает с суставом. Теснота, перечисленная ниже, "
                    "— следствие этого смещения, а не отдельные проблемы."),
            confidence=sm.get("confidence", 0.0),
            check=sm.get("size_hint") or "Подобрать колодку другого размера",
        ))

    # An allowance outside the band is worth saying even when it does not gate.
    # The gate deliberately needs a severe reading or two signals agreeing
    # before it suppresses the zone analysis, but the allowance itself is a
    # plain difference of two lengths -- no landmark detection in it, so no
    # reason to stay silent about it. Skipping that is how a last sitting
    # ~21mm long against a 10-15mm norm reached a wearer with nothing said
    # about its length at all, which is what they then reported back.
    if not sm.get("gate_triggered") and sm.get("length_allowance_mm") is not None:
        allowance = sm["length_allowance_mm"]
        lo, hi = LENGTH_ALLOWANCE_ACCEPTABLE
        if allowance > hi or allowance < lo:
            longish = allowance > hi
            findings.insert(0, Finding(
                severity=WARNING, zone="length",
                title=(f"Припуск по длине {allowance:.0f} мм — "
                       f"{'больше' if longish else 'меньше'} нормы"),
                fact=(f"Колодка длиннее стопы на {allowance:.0f} мм при норме 10–15 мм "
                      f"и допустимых {lo:.0f}–{hi:.0f} мм."),
                effect=("Обувь будет ощущаться длинной: стопа сможет ездить вперёд-назад, "
                        "пучки уйдут назад относительно места сгиба, пятка станет хуже "
                        "держаться." if longish else
                        "Пальцам не хватит места при перекате — упрутся в носок на шаге, "
                        "даже если в статике всё помещается."),
                confidence=sm.get("confidence", 0.0),
                check=("Взять колодку на размер-полтора короче" if longish
                       else "Взять колодку длиннее"),
            ))

    # If the foot had to be swung sideways to sit on this last's axis, every
    # medial/lateral number below partly describes that swing. Said out loud
    # and high up, because otherwise a reader takes "тесно с внутренней
    # стороны" at face value when it may be an artefact of the alignment.
    # Only the severe case is raised as a finding: a swing a little past the
    # measurement noise is true of most real pairs and would just add a
    # permanent warning nobody reads. Milder ones stay in the caveats via the
    # pipeline's limitations.
    reg = report.get("registration") or {}
    if reg.get("axis_mismatch_severe"):
        swing = abs(reg.get("ball_swing_mm") or 0.0)
        findings.insert(0, Finding(
            severity=WARNING, zone="axis",
            title=f"Ось колодки расходится с осью стопы: сдвиг в пучках {swing:.0f} мм",
            fact=(f"Чтобы совместить линию «пятка → пучки» стопы с той же линией колодки, "
                  f"стопу пришлось развернуть на {abs(reg.get('rotation_deg') or 0):.0f}° — "
                  f"в пучках это сдвигает её вбок на {swing:.0f} мм."),
            effect=("Разделение тесноты на «внутреннюю» и «внешнюю» ниже в значительной мере "
                    "описывает этот разворот, а не саму колодку: стопа целиком смещена поперёк "
                    "следа. Общая теснота и длина остаются достоверными, а вот сторона — нет."),
            confidence=reg.get("confidence", 0.0),
            check=("Проверить скан колодки: у одной модели соседние полноты не должны "
                   "давать разный разворот следа относительно пятки"),
        ))

    # A broad, uniform width mismatch on an otherwise correctly-sized last
    # (length and ball line both passed fit_size_match) reads as "wrong width
    # grade", not as six independent tight zones -- the same escalation the
    # size gate does above, one level down.
    fullness_dir = report.get("fullness_direction")
    fullness_mm = report.get("fullness_mm")
    if fit_class == "FIT_REQUIRES_DIFFERENT_FULLNESS" and fullness_dir is not None:
        verb = "шире" if fullness_dir == "wider" else "уже"
        mm = fullness_mm or 0.0
        steps = "2–3" if mm >= 6.0 else "1–2"
        findings.insert(0, Finding(
            severity=CRITICAL, zone="fullness",
            title=f"Размер верный, но полнота не та: нужно примерно на {mm:.0f} мм {verb}",
            fact=("Теснота идёт равномерно по нескольким зонам, а не в одном месте, "
                  "при этом длина колодки и положение пучков в норме — "
                  "это признак полноты, а не размера или локального дефекта."),
            effect=("Точечной растяжкой одной зоны это не лечится — нужна та же модель "
                    "и тот же размер, но другая полнота."),
            confidence=sm.get("confidence", 0.6) if sm else 0.6,
            check=f"Взять колодку той же модели и размера на {steps} ступени {'полнее' if fullness_dir == 'wider' else 'уже'}",
        ))

    tight = [f for f in findings if f.severity in (CRITICAL, WARNING) and "тесно" in f.title]
    loose = [f for f in findings if "свободно" in f.title]
    ok_count = sum(1 for f in findings if f.severity == GOOD)

    if fit_class == "FIT_STRUCTURALLY_INCOMPATIBLE":
        summary = ("Дело не в полноте и не в разноске: колодка не соответствует стопе "
                   "по размеру и пропорции. Нужна колодка другой длины.")
    elif fit_class == "FIT_REQUIRES_DIFFERENT_FULLNESS" and fullness_dir is not None:
        verb = "шире" if fullness_dir == "wider" else "уже"
        summary = (f"Длина колодки и положение пучков в норме. Проблема — полнота: "
                   f"нужно примерно на {(fullness_mm or 0.0):.0f} мм {verb}.")
    elif fit_class == "FIT_REQUIRES_LAST_MODIFICATION":
        summary = ("Теснота и свобода встречаются одновременно в разных зонах — объём "
                   "в колодке есть, но распределён не туда. Ни разноска, ни смена "
                   "полноты сама по себе это не исправит: нужна переделка колодки "
                   "в конкретных зонах, а не другой размерный вариант той же модели.")
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

    # fit_class is derived from the zone clearance alone, so a last can be
    # "GOOD" by zones while carrying a length allowance well outside the band.
    # Saying "Колодка подходит" above a warning that the last is 23mm too long
    # is a contradiction the reader has to resolve themselves, so the headline
    # is qualified whenever anything above neutral was raised.
    headline = _HEADLINE.get(fit_class, fit_class)
    if fit_class == "FIT_GOOD" and any(f.severity in (CRITICAL, WARNING) for f in findings):
        headline = "Подходит с оговорками — см. ниже"

    return Explanation(
        headline=headline,
        summary=summary,
        findings=findings,
        caveats=caveats,
    )
