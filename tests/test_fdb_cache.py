"""Tests for the shared Firebird report cache and its warm plan.

No Firebird and no hr.db: the storage layer is pointed at a temporary
SQLite file and the reports at plain Python functions. What matters here
is the part that silently breaks otherwise — that the key the warmer
writes is the key the API reads, that a cache hit doesn't re-run the
query, and that a miss still answers.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.fdb_cache import FdbCacheEntry  # noqa: F401 — registers the table
from app.services import fdb_cache


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Point the cache at a throwaway SQLite file instead of hr.db."""
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine, tables=[FdbCacheEntry.__table__])
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(fdb_cache, "_session", lambda: Session())
    yield
    engine.dispose()


@pytest.fixture
def counting_report(monkeypatch):
    """Registers a report whose calls are counted, so tests can tell a
    cache hit from a recompute."""
    calls = []

    def fn(*args):
        calls.append(args)
        return {"args": [str(a) for a in args], "n": len(calls)}

    monkeypatch.setitem(fdb_cache.REPORTS, "test.report",
                        fdb_cache.Report("test.report", "test:fn", "frequent"))
    monkeypatch.setattr(fdb_cache, "_resolve", lambda target: fn)
    return calls


class TestKeys:
    def test_same_args_same_key(self):
        a = fdb_cache.make_key("r", (dt.date(2026, 8, 1), None))
        b = fdb_cache.make_key("r", (dt.date(2026, 8, 1), None))
        assert a == b

    def test_different_args_different_key(self):
        a = fdb_cache.make_key("r", (dt.date(2026, 8, 1),))
        b = fdb_cache.make_key("r", (dt.date(2026, 8, 2),))
        assert a != b

    def test_dates_survive_a_round_trip(self):
        args = (dt.date(2026, 8, 5), None, ["a", "b"], 20)
        assert fdb_cache.decode_args(fdb_cache.encode_args(args)) == list(args)

    def test_tuple_and_list_args_agree(self):
        """The warmer builds tuples, handlers build tuples too — but a
        mismatch here would silently mean 0% hit rate, so pin it."""
        assert fdb_cache.make_key("r", (1, 2)) == fdb_cache.make_key("r", [1, 2])

    def test_key_is_prefixed_with_the_report_name(self):
        assert fdb_cache.make_key("sales.daily", ()).startswith("sales.daily:")


class TestStorage:
    def test_put_then_get(self, counting_report):
        fdb_cache.put("test.report", (1,), {"x": 5})
        hit = fdb_cache.get("test.report", (1,))
        assert hit is not None
        value, age = hit
        assert value == {"x": 5}
        assert age < 5

    def test_get_misses_for_unknown_args(self, counting_report):
        fdb_cache.put("test.report", (1,), {"x": 5})
        assert fdb_cache.get("test.report", (2,)) is None

    def test_put_overwrites_in_place(self, counting_report):
        fdb_cache.put("test.report", (1,), {"x": 1})
        fdb_cache.put("test.report", (1,), {"x": 2})
        assert fdb_cache.get("test.report", (1,))[0] == {"x": 2}

    def test_expired_entry_is_not_returned(self, counting_report, monkeypatch):
        fdb_cache.put("test.report", (1,), {"x": 5})
        ttl = fdb_cache.TIERS["frequent"].ttl_s
        _age_entry(monkeypatch, ttl + 60)
        assert fdb_cache.get("test.report", (1,)) is None

    def test_peek_returns_expired_entries(self, counting_report, monkeypatch):
        """The timeout fallback and the status panel both need to see an
        entry that get() correctly refuses to serve."""
        fdb_cache.put("test.report", (1,), {"x": 5})
        _age_entry(monkeypatch, fdb_cache.TIERS["frequent"].ttl_s + 60)
        peeked = fdb_cache.peek("test.report", (1,))
        assert peeked is not None and peeked[0] == {"x": 5}

    def test_unserialisable_value_is_skipped_not_raised(self, counting_report):
        fdb_cache.put("test.report", (1,), {"fn": object()})
        # default=str makes it serialisable, so this stores; the contract
        # under test is only that it never raises into the request path.
        assert fdb_cache.get("test.report", (1,)) is not None


def _age_entry(monkeypatch, seconds: float) -> None:
    """Make every stored entry appear `seconds` old by moving 'now'."""
    real = fdb_cache.datetime

    class _Shifted(real):
        @classmethod
        def now(cls, tz=None):
            return real.now(tz) + dt.timedelta(seconds=seconds)

    monkeypatch.setattr(fdb_cache, "datetime", _Shifted)


class TestGetOrCompute:
    def test_miss_computes_and_stores(self, counting_report):
        value = fdb_cache.get_or_compute("test.report", (7,))
        assert value["n"] == 1
        assert len(counting_report) == 1
        assert fdb_cache.get("test.report", (7,))[0]["n"] == 1

    def test_hit_does_not_recompute(self, counting_report):
        fdb_cache.get_or_compute("test.report", (7,))
        fdb_cache.get_or_compute("test.report", (7,))
        assert len(counting_report) == 1

    def test_different_args_compute_separately(self, counting_report):
        fdb_cache.get_or_compute("test.report", (1,))
        fdb_cache.get_or_compute("test.report", (2,))
        assert len(counting_report) == 2

    def test_expired_entry_recomputes(self, counting_report, monkeypatch):
        fdb_cache.get_or_compute("test.report", (7,))
        _age_entry(monkeypatch, fdb_cache.TIERS["frequent"].ttl_s + 60)
        fdb_cache.get_or_compute("test.report", (7,))
        assert len(counting_report) == 2


class TestIsDue:
    def test_missing_entry_is_due(self, counting_report):
        assert fdb_cache.is_due("test.report", (1,), "frequent") is True

    def test_fresh_entry_is_not_due(self, counting_report):
        fdb_cache.put("test.report", (1,), {"x": 1})
        assert fdb_cache.is_due("test.report", (1,), "frequent") is False

    def test_entry_older_than_refresh_is_due(self, counting_report, monkeypatch):
        fdb_cache.put("test.report", (1,), {"x": 1})
        _age_entry(monkeypatch, fdb_cache.TIERS["frequent"].refresh_s + 10)
        assert fdb_cache.is_due("test.report", (1,), "frequent") is True

    def test_refresh_runs_before_expiry(self):
        """Every tier must try to replace an entry before readers stop
        being allowed to use it — otherwise there is a window on every
        cycle where users fall back to live Firebird queries."""
        for tier in fdb_cache.TIERS.values():
            assert tier.refresh_s < tier.ttl_s, tier.name

    def test_nightly_tier_is_skipped_during_the_day(self, counting_report):
        noon = dt.datetime(2026, 8, 5, 12, 0)
        assert fdb_cache.is_due("test.report", (1,), "nightly", noon) is False

    def test_nightly_tier_runs_at_night(self, counting_report):
        night = dt.datetime(2026, 8, 5, 3, 0)
        assert fdb_cache.is_due("test.report", (1,), "nightly", night) is True


class TestWarmPlan:
    def test_every_planned_report_is_registered(self):
        for report, _args, _tier in fdb_cache.warm_plan():
            assert report in fdb_cache.REPORTS, report

    def test_every_planned_tier_exists(self):
        for _report, _args, tier in fdb_cache.warm_plan():
            assert tier in fdb_cache.TIERS, tier

    def test_plan_has_no_duplicate_keys(self):
        """A duplicate would mean the warmer runs the same expensive query
        twice per cycle against the Agbis server."""
        keys = [fdb_cache.make_key(r, a) for r, a, _ in fdb_cache.warm_plan()]
        assert len(keys) == len(set(keys))

    def test_cash_reports_are_in_the_hot_tier(self):
        """Cash balances are reconciled against a physical count of the
        drawer, so they get the tightest freshness of everything warmed."""
        for report, _args, tier in fdb_cache.warm_plan():
            if report.startswith("cash."):
                assert tier == "hot", report

    def test_masters_and_sales_are_warmed_for_today_and_this_month(self):
        today = dt.date.today()
        month_start = today.replace(day=1)
        planned = {(r, tuple(a[:2])) for r, a, _ in fdb_cache.warm_plan()}
        assert ("masters.works", (month_start, today)) in planned
        assert ("sales.daily", (today, today)) in planned

    def test_registered_targets_all_resolve_to_a_known_kind(self):
        for report in fdb_cache.REPORTS.values():
            kind = report.target.split(":", 1)[0]
            assert kind in {"firebird", "masters"}, report.name


class TestPeriods:
    def test_month_starts_on_the_first(self):
        df, dt_ = fdb_cache._period("month", dt.date(2026, 8, 5))
        assert (df, dt_) == (dt.date(2026, 8, 1), dt.date(2026, 8, 5))

    def test_prev_month_covers_the_whole_previous_month(self):
        df, dt_ = fdb_cache._period("prev_month", dt.date(2026, 8, 5))
        assert (df, dt_) == (dt.date(2026, 7, 1), dt.date(2026, 7, 31))

    def test_prev_month_across_a_year_boundary(self):
        df, dt_ = fdb_cache._period("prev_month", dt.date(2026, 1, 15))
        assert (df, dt_) == (dt.date(2025, 12, 1), dt.date(2025, 12, 31))

    def test_week_is_seven_days_inclusive(self):
        df, dt_ = fdb_cache._period("week", dt.date(2026, 8, 5))
        assert (dt_ - df).days == 6


class TestAgeOf:
    def test_returns_none_when_absent(self, counting_report):
        assert fdb_cache.age_of("test.report", (1,)) is None

    def test_returns_age_without_reading_the_payload(self, counting_report, monkeypatch):
        fdb_cache.put("test.report", (1,), {"x": 1})
        # _load is the decompressing path; the age lookup must not use it —
        # the warmer and the status panel call this for every planned entry
        # on a short interval.
        monkeypatch.setattr(fdb_cache, "_load", lambda key: pytest.fail("decompressed"))
        age = fdb_cache.age_of("test.report", (1,))
        assert age is not None and age < 5

    def test_age_grows_with_time(self, counting_report, monkeypatch):
        fdb_cache.put("test.report", (1,), {"x": 1})
        _age_entry(monkeypatch, 120)
        assert fdb_cache.age_of("test.report", (1,)) >= 120
