"""Is this last the right *size and proportion* for this foot at all?

Runs before the zone-by-zone analysis and can override it. The reason is a real
case: a 250mm foot against a 288mm last produced six zones of "tightness" and
never said the obvious thing -- the last is two-and-a-half sizes too long, so
the foot's ball lands 16mm behind the last's ball, in the narrower waist. Every
one of those six findings was a *consequence* of that, presented as an
independent problem. §15.3 of the research report calls this "неправильная
heel-to-ball length" and treats it as structural incompatibility, not local
tightness; §9 of the audit says the same about length.

Two checks, both deliberately not measured the naive way:

- Toe allowance is measured to the *functional* end of the toe box, not to the
  decorative tip (§9 of the audit). A classic last can carry 20mm of pure
  styling past the point where the toe box still has usable height, and
  counting that as room for toes is how a far-too-long last passes a length
  check. The functional end is where the cavity's height drops below the
  height of *this client's* longest toe -- tied to the actual foot rather than
  to a universal constant, which is what §22.3 asks for.

- Ball-line offset is expressed as a fraction of foot length, so one threshold
  works across the whole size grading instead of being strict on a 38 and
  loose on a 46.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh

from app.services.foot_landmarks import FootLandmarks

# Functional toe allowance, mm. Classic men's leather footwear. These are
# documented starting values, NOT calibrated against real fittings -- §29 asks
# for a fitting pilot before any threshold is treated as fact.
#
# The lower bound widened from 8mm to 5mm after a real pair (functional
# clearance 7.0mm, ball offset -2.0% -- both otherwise unremarkable) tripped
# the gate on that single millimetre and reported "wrong length" for a last
# whose actual problem was width. See _classify_toe/_is_severe below for how
# a value this close to the edge is now handled even when it IS outside the
# band.
TOE_ALLOWANCE_GOOD = (10.0, 15.0)
TOE_ALLOWANCE_ACCEPTABLE = (5.0, 20.0)
# Past this far beyond the acceptable band, the reading is unambiguous enough
# to gate on its own, without needing the other signal to agree.
_TOE_SEVERE_MARGIN_MM = 10.0

# Ball-line offset as a fraction of foot length.
BALL_OFFSET_GOOD = 0.02
BALL_OFFSET_GATE = 0.04
# Same idea as _TOE_SEVERE_MARGIN_MM: an offset this far past the gate
# threshold is unambiguous on its own.
BALL_OFFSET_SEVERE = 0.08

# Below this landmark confidence the gate is demoted to an ordinary finding:
# a bad MTH detection would otherwise silence every real zone result.
MIN_GATE_CONFIDENCE = 0.4

# European size step, mm -- used only to phrase "about N sizes", never to
# assert a size number.
_SIZE_STEP_MM = 6.67

_TOE_BAND_MM = 12.0
_MIN_BAND_POINTS = 4


@dataclass
class SizeMatch:
    functional_toe_clearance_mm: float | None
    total_length_excess_mm: float | None
    functional_toe_end_y_mm: float | None
    ball_offset_mm: float | None
    ball_offset_fraction: float | None
    confidence: float
    gate_triggered: bool
    reasons: list[str] = field(default_factory=list)
    size_hint: str | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "functional_toe_clearance_mm": _r(self.functional_toe_clearance_mm),
            "total_length_excess_mm": _r(self.total_length_excess_mm),
            "functional_toe_end_y_mm": _r(self.functional_toe_end_y_mm),
            "ball_offset_mm": _r(self.ball_offset_mm),
            "ball_offset_pct": (round(self.ball_offset_fraction * 100, 1)
                                if self.ball_offset_fraction is not None else None),
            "confidence": round(self.confidence, 3),
            "gate_triggered": self.gate_triggered,
            "reasons": list(self.reasons),
            "size_hint": self.size_hint,
            "warnings": list(self.warnings),
        }


def _r(v: float | None) -> float | None:
    return None if v is None else round(v, 1)


def _height_at(mesh: trimesh.Trimesh, y: float, band: float = _TOE_BAND_MM) -> float | None:
    v = np.asarray(mesh.vertices, dtype=float)
    m = np.abs(v[:, 1] - y) <= band / 2.0
    if m.sum() < _MIN_BAND_POINTS:
        return None
    return float(v[m, 2].max() - v[m, 2].min())


def _functional_toe_end(cavity: trimesh.Trimesh, from_y: float,
                        required_height_mm: float) -> float | None:
    """Furthest point forward where the cavity still stands at least as tall as
    the foot's own longest toe. Past that the toe box is decoration."""
    v = np.asarray(cavity.vertices, dtype=float)
    y_max = float(v[:, 1].max())
    if y_max <= from_y:
        return None
    steps = np.arange(from_y, y_max + 1.0, 2.0)
    last_ok = None
    for y in steps:
        h = _height_at(cavity, float(y))
        if h is None:
            continue
        if h >= required_height_mm:
            last_ok = float(y)
        elif last_ok is not None:
            break  # the box has dropped below usable height and stays there
    return last_ok


def evaluate_size_match(
    foot_mesh: trimesh.Trimesh,
    cavity_mesh: trimesh.Trimesh,
    foot_landmarks: FootLandmarks,
    last_landmarks: FootLandmarks,
) -> SizeMatch:
    """Both meshes must already be in one frame (heel-fixed registration)."""
    warnings: list[str] = []
    reasons: list[str] = []

    fv = np.asarray(foot_mesh.vertices, dtype=float)
    foot_y_min, foot_y_max = float(fv[:, 1].min()), float(fv[:, 1].max())
    foot_length = foot_y_max - foot_y_min
    cavity_y_max = float(np.asarray(cavity_mesh.vertices)[:, 1].max())
    total_excess = cavity_y_max - foot_y_max

    # --- functional toe allowance ---------------------------------------
    toe_height = _height_at(foot_mesh, foot_y_max - _TOE_BAND_MM / 2.0)
    functional_end = None
    functional_clearance = None
    if toe_height is None:
        warnings.append("toe_height_unmeasurable")
    else:
        ball_y = (foot_landmarks.ball_center[1]
                  if foot_landmarks.ball_center is not None else foot_y_min + 0.6 * foot_length)
        functional_end = _functional_toe_end(cavity_mesh, ball_y, toe_height)
        if functional_end is None:
            warnings.append("functional_toe_end_not_found")
        else:
            functional_clearance = functional_end - foot_y_max

    # --- ball line offset -------------------------------------------------
    ball_offset = None
    ball_fraction = None
    fb = foot_landmarks.ball_center
    lb = last_landmarks.ball_center
    if fb is None or lb is None:
        warnings.append("ball_center_missing")
    else:
        ball_offset = float(lb[1] - fb[1])
        ball_fraction = ball_offset / foot_length if foot_length > 0 else None

    confidence = min(foot_landmarks.confidence, last_landmarks.confidence)

    # --- gate ---------------------------------------------------------
    # A single measurement landing just past its own edge is not enough by
    # itself: on a real pair, functional clearance of 7.0mm (0.9mm past the
    # then-8mm edge) gated alone and reported "wrong length" for a last that
    # actually fit lengthwise -- its real problem (an 8mm width deficit at the
    # ball) only showed up in the zone analysis this gate had suppressed.
    #
    # So each signal is graded two ways: past its normal edge ("out"), and far
    # enough past it to be unambiguous on its own ("severe", via the *_SEVERE
    # margins/thresholds above). The gate fires only when at least one signal
    # is severe, or when both signals are simultaneously out -- two
    # independent measurements agreeing is itself evidence, even if neither
    # alone clears the severe bar.
    toe_out_reason: str | None = None
    toe_severe = False
    if functional_clearance is not None:
        lo, hi = TOE_ALLOWANCE_ACCEPTABLE
        if functional_clearance > hi:
            toe_out_reason = f"functional toe allowance {functional_clearance:.0f}mm exceeds {hi:.0f}mm"
            toe_severe = functional_clearance > hi + _TOE_SEVERE_MARGIN_MM
        elif functional_clearance < lo:
            toe_out_reason = f"functional toe allowance {functional_clearance:.0f}mm below {lo:.0f}mm"
            toe_severe = functional_clearance < lo - _TOE_SEVERE_MARGIN_MM

    ball_out_reason: str | None = None
    ball_severe = False
    if ball_fraction is not None and abs(ball_fraction) > BALL_OFFSET_GATE:
        ball_out_reason = (f"ball line offset {abs(ball_fraction) * 100:.1f}% of foot length "
                           f"exceeds {BALL_OFFSET_GATE * 100:.0f}%")
        ball_severe = abs(ball_fraction) > BALL_OFFSET_SEVERE

    gate = False
    if toe_severe:
        gate = True
        reasons.append(toe_out_reason)
    if ball_severe:
        gate = True
        reasons.append(ball_out_reason)
    if not gate and toe_out_reason is not None and ball_out_reason is not None:
        gate = True
        reasons.append(toe_out_reason)
        reasons.append(ball_out_reason)
        reasons.append("neither signal alone was severe, but both agree")

    if gate and confidence < MIN_GATE_CONFIDENCE:
        # A weak landmark set must not be allowed to silence the zone analysis.
        gate = False
        warnings.append("size_mismatch_suspected_but_landmark_confidence_too_low_for_a_verdict")

    # --- direction to look in --------------------------------------------
    size_hint = None
    if gate and functional_clearance is not None:
        target = sum(TOE_ALLOWANCE_GOOD) / 2.0
        delta = functional_clearance - target
        if abs(delta) >= _SIZE_STEP_MM:
            steps = abs(delta) / _SIZE_STEP_MM
            direction = "меньше" if delta > 0 else "больше"
            want_ball = ((foot_landmarks.ball_center[1] - foot_y_min)
                         if foot_landmarks.ball_center is not None else None)
            hint = (f"колодка {'длиннее' if delta > 0 else 'короче'} нужного примерно на "
                    f"{abs(delta):.0f} мм — смотрите на {steps:.0f}–{steps + 1:.0f} размера {direction}")
            if want_ball is not None:
                hint += f"; пучки должны лечь примерно на {want_ball:.0f} мм от пятки"
            size_hint = hint

    return SizeMatch(
        functional_toe_clearance_mm=functional_clearance,
        total_length_excess_mm=total_excess,
        functional_toe_end_y_mm=functional_end,
        ball_offset_mm=ball_offset,
        ball_offset_fraction=ball_fraction,
        confidence=confidence,
        gate_triggered=gate,
        reasons=reasons,
        size_hint=size_hint,
        warnings=warnings,
    )
