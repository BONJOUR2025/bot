"""Golden-reference regression test for the slice_v1 pipeline
(scm_parser_service.extract_profile + last_fit_service.compare_profiles).

Frozen as of the slice_v1 -> hybrid_v2 migration (see
docs/last_fit_system_overview.md and the migration plan): slice_v1 must keep
producing exactly these numbers going forward, even as hybrid_v2 is built
alongside it. If this test fails after a change to scm_parser_service.py or
last_fit_service.py, that change altered slice_v1's behavior — confirm that's
actually intended (and update this snapshot deliberately) rather than an
accidental side effect.

Synthetic geometry only (no real client scans) — deterministic via a seeded
RNG, so the same two "foot" and "last" point clouds are reproduced every run.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.services.last_fit_service import compare_profiles
from app.services.scm_parser_service import (
    FootBlock,
    _ball_line_mm,
    _instep_girth,
    extract_profile,
)

RNG_SEED = 7


def _half_width(frac: np.ndarray) -> np.ndarray:
    return 20.0 + 20.0 * np.exp(-((frac - 0.65) ** 2) / (2 * 0.2 ** 2))


def _half_height(frac: np.ndarray) -> np.ndarray:
    return 20.0 + 15.0 * np.exp(-((frac - 0.35) ** 2) / (2 * 0.25 ** 2))


def _make_block(rng: np.random.Generator, n: int = 8000, length_mm: float = 270.0,
                 width_scale: float = 1.0, height_scale: float = 1.0) -> FootBlock:
    y = rng.uniform(0.0, length_mm, n)
    frac = y / length_mm
    hw = _half_width(frac) * width_scale
    hh = _half_height(frac) * height_scale
    x = rng.uniform(-1.0, 1.0, n) * hw
    z = rng.uniform(0.0, 1.0, n) * hh
    return FootBlock(byte_start=0, byte_end=0, x=x, y=y.astype(float), z=z.astype(float))


def _profile_dict(block: FootBlock) -> dict:
    profile = extract_profile(block)
    return {
        **profile,
        "ball_girth_mm": block.ball_girth_mm,
        "instep_girth_mm": _instep_girth(block),
        "ball_line_mm": _ball_line_mm(block.x, block.y),
    }


@pytest.fixture(scope="module")
def golden_result() -> dict:
    rng = np.random.default_rng(RNG_SEED)
    foot_block = _make_block(rng, length_mm=270.0, width_scale=1.0, height_scale=1.0)
    last_block = _make_block(rng, length_mm=282.0, width_scale=1.05, height_scale=1.08)
    foot = _profile_dict(foot_block)
    last = _profile_dict(last_block)
    return compare_profiles(foot, last, foot_side="left", last_side="left")


def test_overall_verdict_frozen(golden_result):
    assert golden_result["overall"] == "not_fit"
    assert golden_result["hard_fail_reasons"] == []
    assert golden_result["overlap_pct"] == pytest.approx(100.0, abs=0.5)


def test_zone_verdicts_frozen(golden_result):
    verdicts = {z["zone"]: z["verdict"] for z in golden_result["zones"]}
    assert verdicts == {
        "heel": "ideal",
        "waist": "ideal",
        "instep": "uncertain",
        "ball": "too_tight",
        "toe": "ideal",
    }


def test_length_and_girths_frozen(golden_result):
    length = golden_result["length"]
    assert length["foot_mm"] == pytest.approx(269.8, abs=0.2)
    assert length["last_mm"] == pytest.approx(281.9, abs=0.2)
    assert length["verdict"] == "ideal"

    ball = golden_result["girths"]["ball"]
    assert ball["ease_mm"] == pytest.approx(-16.3, abs=0.5)

    instep = golden_result["girths"]["instep"]
    assert instep["ease_mm"] == pytest.approx(11.3, abs=0.5)
