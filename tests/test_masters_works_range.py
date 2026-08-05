"""Tests for the /masters/works date-range guard.

The endpoint used to accept no dates at all and answer with the entire
history: measured against production that was 100 MB of JSON after 123 s,
holding a Firebird connection the whole time. The frontend always sends a
range, so this only ever constrains direct API callers — but one such call
is enough to evict everyone else's pages from the OS file cache.
"""
from __future__ import annotations

import datetime as dt

from app.services.masters_service import MAX_WORKS_RANGE_DAYS, resolve_works_range


class TestDefaults:
    def test_no_dates_means_the_current_month(self):
        df, to, clamped = resolve_works_range(None, None)
        today = dt.date.today()
        assert to == today
        assert df == today.replace(day=1)
        assert clamped is False

    def test_only_date_to_backfills_that_month(self):
        df, to, clamped = resolve_works_range(None, dt.date(2026, 8, 20))
        assert (df, to) == (dt.date(2026, 8, 1), dt.date(2026, 8, 20))
        assert clamped is False

    def test_only_date_from_runs_to_today(self):
        df, to, _ = resolve_works_range(dt.date(2026, 8, 1), None)
        assert df == dt.date(2026, 8, 1)
        assert to == dt.date.today()


class TestClamping:
    def test_explicit_range_within_the_cap_is_untouched(self):
        df, to, clamped = resolve_works_range(dt.date(2026, 7, 1), dt.date(2026, 8, 5))
        assert (df, to) == (dt.date(2026, 7, 1), dt.date(2026, 8, 5))
        assert clamped is False

    def test_range_exactly_at_the_cap_is_not_clamped(self):
        to = dt.date(2026, 8, 5)
        df = to - dt.timedelta(days=MAX_WORKS_RANGE_DAYS - 1)
        assert resolve_works_range(df, to) == (df, to, False)

    def test_range_over_the_cap_is_trimmed_from_the_start(self):
        df, to, clamped = resolve_works_range(dt.date(2013, 1, 1), dt.date(2026, 8, 5))
        assert clamped is True
        assert to == dt.date(2026, 8, 5)
        assert (to - df).days + 1 == MAX_WORKS_RANGE_DAYS

    def test_reversed_range_is_swapped_before_clamping(self):
        df, to, clamped = resolve_works_range(dt.date(2026, 8, 5), dt.date(2026, 7, 1))
        assert (df, to) == (dt.date(2026, 7, 1), dt.date(2026, 8, 5))
        assert clamped is False

    def test_single_day_is_allowed(self):
        d = dt.date(2026, 8, 5)
        assert resolve_works_range(d, d) == (d, d, False)
