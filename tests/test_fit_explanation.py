"""Tests for fit_explanation -- the plain-language layer over a clearance
report. Built on hand-crafted report dicts rather than real meshes: the
things being checked here are about which words get attached to which
number, not about the geometry that produced it."""
from __future__ import annotations

from app.services.fit_explanation import explain


def _zone(name, median, directional, classification, p95=8.0, area=500.0, confidence=0.9):
    return {
        "name": name,
        "signed_gap_mm": {"min": median - 5, "p05": median - 4, "median": median, "p95": median + 4},
        "required_compression_mm": {"p95": p95},
        "conflict_area_mm2": area,
        "directional_mm": directional,
        "seating_gap_mm": None,
        "classification": classification,
        "confidence": confidence,
    }


def _report(zones, sigma=2.69, **extra):
    return {
        "fit_class": extra.pop("fit_class", "FIT_LOCAL_TIGHTNESS"),
        "fullness_direction": None,
        "fullness_mm": None,
        "registration": extra.pop("registration", {}),
        "size_match": extra.pop("size_match", {}),
        "limitations": [],
        "clearance": {
            "zones": zones,
            "uncertainty": {"total_sigma_mm": sigma},
        },
        **extra,
    }


def _finding(report, zone_name):
    findings = explain(report).findings
    return next(f for f in findings if f.zone == zone_name)


def test_a_tail_only_tight_zone_is_not_blamed_on_plantar():
    """The real defect: a zone earns LOCAL_TIGHTNESS through its p05 tail, not
    through any single direction crossing the bar, and the worst raw number
    happens to be plantar. fit_clearance's own classifier excludes plantar
    from what counts as a squeeze (a negative plantar gap is seating, the
    foot resting on the insole, not a press) -- so attributing the finding to
    "снизу" contradicts the very module that produced it. On a real last,
    three zones classified tight this way all had their finding blamed on
    plantar when direct geometry confirmed a lateral squeeze in every one."""
    z = _zone("waist", median=-3.81,
              directional={"medial": -3.76, "lateral": -4.66, "dorsal": None, "plantar": -5.28},
              classification="LOCAL_TIGHTNESS")
    f = _finding(_report([z]), "waist")
    assert "снизу" not in f.title
    assert "внешней" in f.title  # lateral, the true worst non-plantar direction


def test_plantar_alone_never_produces_a_direction_word():
    """If every horizontal direction is fine and only plantar reads negative,
    there is no honest "where" to report -- the finding must not invent one
    from the direction fit_clearance itself excludes."""
    z = _zone("ball", median=-6.0,
              directional={"medial": 1.0, "lateral": 0.5, "dorsal": 2.0, "plantar": -8.0},
              classification="LOCAL_TIGHTNESS")
    f = _finding(_report([z]), "ball")
    assert "снизу" not in f.title
    assert "с внутренней стороны" not in f.title
    assert "с внешней стороны" not in f.title
    assert "сверху" not in f.title


def test_a_one_sided_press_inside_within_uncertainty_is_not_silenced():
    """A zone can read as fine in aggregate (median inside sigma) while one
    side sits meaningfully past the noise floor -- past 1 sigma, though not
    past fit_clearance's stricter 2-sigma bar for calling the zone itself
    tight. On a real last this stayed invisible: two WITHIN_UNCERTAINTY zones
    carried a -3.18mm and a -2.41mm medial press respectively and neither
    number appeared anywhere in the report."""
    sigma = 2.69
    z = _zone("heel", median=-0.74,
              directional={"medial": -3.18, "lateral": 0.41, "dorsal": None, "plantar": -2.33},
              classification="WITHIN_UNCERTAINTY")
    f = _finding(_report([z], sigma=sigma), "heel")
    assert "3" in f.fact  # the ~3.18mm press is stated, not dropped
    assert f.severity == "good"  # fit_clearance's own verdict is not overridden


def test_a_uniform_zone_carries_no_caveat():
    """The caveat is only for a genuine one-sided press. A zone with no
    direction past 1 sigma must read as plainly fine, not hedge for no
    reason."""
    z = _zone("instep", median=0.5,
              directional={"medial": 0.2, "lateral": -0.4, "dorsal": 0.8, "plantar": -0.6},
              classification="WITHIN_UNCERTAINTY")
    f = _finding(_report([z]), "instep")
    assert "поджатие" not in f.fact


def test_loose_zone_with_a_one_sided_press_states_it_too():
    """The same dilution applies to a zone that reads loose overall -- a real
    press on one side does not stop being real because the zone average is
    positive."""
    z = _zone("ball", median=6.5,
              directional={"medial": -3.5, "lateral": 2.0, "dorsal": 8.0, "plantar": -1.0},
              classification="LOCAL_LOOSENESS")
    f = _finding(_report([z]), "ball")
    assert f.severity == "warning"
    assert "поджатие" in f.fact
