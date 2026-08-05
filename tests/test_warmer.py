"""Tests for the cache warmer's cycle logic.

Firebird, hr.db and Telegram are all stubbed. What is worth pinning down
is the behaviour that protects the Agbis server and the operator: one
query at a time with a pause after each, failures never crashing the
loop, and an alert that fires on a persistent problem without spamming.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app import warmer as warmer_mod
from app.warmer import ALERT_AFTER_FAILURES, Warmer


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Record pauses instead of taking them."""
    slept: list[float] = []
    monkeypatch.setattr(warmer_mod.time, "sleep", lambda s: slept.append(s))
    return slept


@pytest.fixture
def alerts(monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(warmer_mod, "notify", lambda text: sent.append(text))
    return sent


def _plan(monkeypatch, entries):
    monkeypatch.setattr(warmer_mod.fdb_cache, "warm_plan", lambda now=None: iter(entries))


def _due(monkeypatch, value=True):
    monkeypatch.setattr(warmer_mod.fdb_cache, "is_due", lambda *a, **k: value)


class TestRunPass:
    def test_computes_every_due_entry(self, monkeypatch, alerts):
        computed = []
        _plan(monkeypatch, [("a", (), "hot"), ("b", (), "frequent")])
        _due(monkeypatch, True)
        monkeypatch.setattr(Warmer, "compute", lambda self, r, a: computed.append(r))
        result = Warmer().run_pass()
        assert computed == ["a", "b"]
        assert result["warmed"] == 2
        assert result["failed"] == 0

    def test_skips_entries_that_are_not_due(self, monkeypatch, alerts):
        computed = []
        _plan(monkeypatch, [("a", (), "hot")])
        _due(monkeypatch, False)
        monkeypatch.setattr(Warmer, "compute", lambda self, r, a: computed.append(r))
        result = Warmer().run_pass()
        assert computed == []
        assert result["skipped"] == 1
        assert result["warmed"] == 0

    def test_one_failing_report_does_not_stop_the_rest(self, monkeypatch, alerts):
        computed = []

        def compute(report, args):
            if report == "bad":
                raise RuntimeError("firebird angry")
            computed.append(report)

        _plan(monkeypatch, [("bad", (), "hot"), ("good", (), "hot")])
        _due(monkeypatch, True)
        monkeypatch.setattr(Warmer, "compute", lambda self, r, a: compute(r, a))
        result = Warmer().run_pass()
        assert computed == ["good"]
        assert result["failed"] == 1
        assert result["warmed"] == 1
        assert any("firebird angry" in e for e in result["errors"])

    def test_pauses_after_every_query_including_failures(self, monkeypatch, alerts, no_sleep):
        """Rule 2 in the module docstring: a loaded server is exactly when
        backing off matters, and a failing query usually means loaded."""
        def compute(report, args):
            raise RuntimeError("nope")

        _plan(monkeypatch, [("a", (), "hot"), ("b", (), "hot")])
        _due(monkeypatch, True)
        monkeypatch.setattr(Warmer, "compute", lambda self, r, a: compute(r, a))
        Warmer().run_pass()
        assert len(no_sleep) == 2
        assert all(s >= warmer_mod.MIN_PAUSE_S for s in no_sleep)

    def test_no_pause_for_skipped_entries(self, monkeypatch, alerts, no_sleep):
        _plan(monkeypatch, [("a", (), "hot")])
        _due(monkeypatch, False)
        Warmer().run_pass()
        assert no_sleep == []

    def test_pause_is_capped(self, monkeypatch, alerts, no_sleep):
        _plan(monkeypatch, [("a", (), "hot")])
        _due(monkeypatch, True)

        # A query that "took" far longer than MAX_PAUSE_S/PACING_RATIO.
        real_time = warmer_mod.time.time
        ticks = iter([0.0, 0.0, 10_000.0, 10_000.0, 10_000.0, 10_000.0])
        monkeypatch.setattr(warmer_mod.time, "time", lambda: next(ticks, 10_000.0))
        monkeypatch.setattr(Warmer, "compute", lambda self, r, a: None)
        Warmer().run_pass()
        assert no_sleep and no_sleep[0] <= warmer_mod.MAX_PAUSE_S
        warmer_mod.time.time = real_time

    def test_reports_how_busy_firebird_was(self, monkeypatch, alerts):
        _plan(monkeypatch, [("a", (), "hot")])
        _due(monkeypatch, True)
        monkeypatch.setattr(Warmer, "compute", lambda self, r, a: None)
        result = Warmer().run_pass()
        assert "busy_pct" in result and result["busy_pct"] >= 0
        assert "firebird_busy_s" in result


class TestAlerting:
    def test_no_alert_on_a_single_failure(self, alerts):
        w = Warmer()
        w.handle_result({"warmed": 0, "failed": 1, "errors": ["boom"]})
        assert alerts == []

    def test_alerts_after_repeated_failures(self, alerts):
        w = Warmer()
        for _ in range(ALERT_AFTER_FAILURES):
            w.handle_result({"warmed": 0, "failed": 1, "errors": ["boom"]})
        assert len(alerts) == 1
        assert "не работает" in alerts[0]

    def test_partial_failure_still_counts(self, alerts):
        """A single report failing on every pass while the others succeed
        would otherwise never be surfaced anywhere."""
        w = Warmer()
        for _ in range(ALERT_AFTER_FAILURES):
            w.handle_result({"warmed": 5, "failed": 1, "errors": ["one bad report"]})
        assert len(alerts) == 1

    def test_does_not_realert_immediately(self, alerts):
        w = Warmer()
        for _ in range(ALERT_AFTER_FAILURES + 5):
            w.handle_result({"warmed": 0, "failed": 1, "errors": ["boom"]})
        assert len(alerts) == 1

    def test_clean_cycle_resets_the_counter(self, alerts):
        w = Warmer()
        w.handle_result({"warmed": 0, "failed": 1, "errors": []})
        w.handle_result({"warmed": 3, "failed": 0, "errors": []})
        assert w.consecutive_failures == 0
        assert alerts == []

    def test_recovery_is_announced_only_after_an_alert(self, alerts):
        w = Warmer()
        for _ in range(ALERT_AFTER_FAILURES):
            w.handle_result({"warmed": 0, "failed": 1, "errors": ["boom"]})
        w.handle_result({"warmed": 3, "failed": 0, "errors": []})
        assert len(alerts) == 2
        assert "восстановился" in alerts[1]

    def test_no_recovery_message_without_a_preceding_alert(self, alerts):
        w = Warmer()
        w.handle_result({"warmed": 0, "failed": 1, "errors": []})
        w.handle_result({"warmed": 3, "failed": 0, "errors": []})
        assert alerts == []


class TestHeartbeat:
    def test_heartbeat_carries_the_last_cycle_summary(self, monkeypatch, alerts):
        captured = {}
        monkeypatch.setattr(warmer_mod, "write_heartbeat",
                            lambda name, **kw: captured.update({"name": name, **kw}))
        w = Warmer()
        w.last_cycle = {"warmed": 2, "failed": 0, "cycle_s": 3.5,
                        "busy_pct": 40.0, "errors": ["should not be sent"]}
        w.heartbeat()
        assert captured["name"] == warmer_mod.HEARTBEAT_NAME
        assert captured["warmed"] == 2
        # Error strings can be long and are shown in the cache panel instead.
        assert "errors" not in captured


class TestBusyMetric:
    def test_duty_cycle_counts_the_idle_gap_between_passes(self, monkeypatch, alerts):
        """busy_pct is what the operator reads to judge how much load the
        warmer puts on the Agbis server. Measuring it against the pass
        duration alone would report ~27% for a warmer that in fact works
        3s out of every 40 — the idle gap has to be in the denominator."""
        _plan(monkeypatch, [("a", (), "hot")])
        _due(monkeypatch, True)
        monkeypatch.setattr(Warmer, "compute", lambda self, r, a: None)

        # t: pass1 start=0, query 0->2, pass1 end=2; pass2 start=40, query
        # 40->42, pass2 end=42.  Window for pass 2 is 40s, busy is 2s.
        ticks = iter([0.0, 0.0, 2.0, 2.0, 40.0, 40.0, 42.0, 42.0])
        monkeypatch.setattr(warmer_mod.time, "time", lambda: next(ticks, 42.0))

        w = Warmer()
        w.run_pass()
        second = w.run_pass()
        assert second["firebird_busy_s"] == 2.0
        assert second["busy_pct"] == 5.0
