"""Tests for FirebirdService.get_daily_cash_balances — the opening/closing
per-day cash report.

Firebird is stubbed out at _connect(): what's worth testing here is the
part that isn't SQL — carrying the running balance across days, emitting
days that have no documents at all, and netting инкассация separately
from приход/расход. The SQL itself was verified against production
(register 5_Гранд Палас, 01.08.2026: opening 17594 → closing 22788,
matching what the Agbis report and the employee's physical count said).
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.services import firebird_service as fb
from app.services.firebird_service import FirebirdService


class _FakeCursor:
    """Dispatches on the SQL text, since get_daily_cash_balances runs its
    four queries through one cursor in a fixed order."""

    def __init__(self, baseline, daily, entries, kassa_name):
        self._baseline = baseline
        self._daily = daily
        self._entries = entries
        self._kassa_name = kassa_name
        self._result = None

    def execute(self, sql, params=None):
        lowered = " ".join(sql.lower().split())
        if "from kasses" in lowered:
            self._result = [(self._kassa_name,)]
        elif "group by d.doc_date" in lowered:
            self._result = list(self._daily)
        elif "doc_kassa_basises" in lowered:
            self._result = list(self._entries)
        else:
            self._result = [(self._baseline,)]

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return self._result


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


@pytest.fixture
def stub_firebird(monkeypatch):
    """Installs canned query results and returns the connection object so
    a test can assert it was closed."""
    holder = {}

    def install(baseline=0.0, daily=(), entries=(), kassa_name="5_Пассаж"):
        conn = _FakeConn(_FakeCursor(baseline, daily, entries, kassa_name))
        holder["conn"] = conn
        monkeypatch.setattr(fb, "_connect", lambda *a, **k: conn)
        monkeypatch.setattr(fb, "FIREBIRD_AVAILABLE", True)
        return conn

    install.holder = holder
    return install


def _day(d):
    return dt.date.fromisoformat(d)


class TestDayRows:
    def test_running_balance_carries_across_days(self, stub_firebird):
        stub_firebird(
            baseline=1000.0,
            # (doc_date, income, expense, collection, count)
            daily=[
                (_day("2026-08-01"), 500.0, 0.0, 0.0, 1),
                (_day("2026-08-02"), 300.0, 100.0, 0.0, 2),
            ],
        )
        res = FirebirdService().get_daily_cash_balances(21066, _day("2026-08-01"), _day("2026-08-02"))

        assert res["opening"] == 1000.0
        assert [d["opening"] for d in res["days"]] == [1000.0, 1500.0]
        assert [d["closing"] for d in res["days"]] == [1500.0, 1700.0]
        # Each day's opening is the previous day's closing — the property the
        # whole report is read for.
        assert res["days"][1]["opening"] == res["days"][0]["closing"]
        assert res["closing"] == 1700.0

    def test_days_without_documents_are_still_rows(self, stub_firebird):
        """The 02.08.2026 shortfall case: the ledger recorded nothing that
        day, and the report has to say so out loud rather than skip the
        row, otherwise "no data" and "nothing moved" look identical."""
        stub_firebird(
            baseline=17594.0,
            daily=[(_day("2026-08-01"), 5194.0, 0.0, 0.0, 2)],
        )
        res = FirebirdService().get_daily_cash_balances(21066, _day("2026-08-01"), _day("2026-08-03"))

        assert [d["date"] for d in res["days"]] == ["2026-08-01", "2026-08-02", "2026-08-03"]
        quiet = res["days"][1]
        assert quiet["entry_count"] == 0
        assert quiet["income"] == quiet["expense"] == quiet["collection"] == 0.0
        assert quiet["opening"] == quiet["closing"] == 22788.0

    def test_single_day_range(self, stub_firebird):
        stub_firebird(baseline=50.0, daily=[(_day("2026-08-01"), 10.0, 0.0, 0.0, 1)])
        res = FirebirdService().get_daily_cash_balances(21066, _day("2026-08-01"), _day("2026-08-01"))
        assert len(res["days"]) == 1
        assert res["days"][0]["closing"] == 60.0

    def test_reversed_range_is_swapped_not_empty(self, stub_firebird):
        stub_firebird(baseline=0.0, daily=[])
        res = FirebirdService().get_daily_cash_balances(21066, _day("2026-08-05"), _day("2026-08-03"))
        assert res["date_from"] == "2026-08-03"
        assert res["date_to"] == "2026-08-05"
        assert len(res["days"]) == 3


class TestInkassation:
    def test_collection_reduces_balance_and_stays_out_of_expense(self, stub_firebird):
        stub_firebird(
            baseline=28058.0,
            daily=[(_day("2026-07-30"), 0.0, 0.0, 12000.0, 1)],
        )
        res = FirebirdService().get_daily_cash_balances(21066, _day("2026-07-30"), _day("2026-07-30"))
        row = res["days"][0]
        assert row["collection"] == 12000.0
        assert row["expense"] == 0.0
        assert row["closing"] == 16058.0

    def test_negative_collection_is_a_top_up_and_raises_balance(self, stub_firebird):
        """A register can be topped up *from* Основная under the same
        Инкассация basis ("Приход с кассы: Основная"). Net инкассация goes
        negative there, and the balance must go up — the reason приход is
        not just SUM(debet) over every basis."""
        stub_firebird(
            baseline=1000.0,
            daily=[(_day("2026-07-27"), 0.0, 0.0, -654.0, 1)],
        )
        res = FirebirdService().get_daily_cash_balances(21066, _day("2026-07-27"), _day("2026-07-27"))
        row = res["days"][0]
        assert row["collection"] == -654.0
        assert row["income"] == 0.0
        assert row["closing"] == 1654.0

    def test_row_arithmetic_closes_on_a_mixed_day(self, stub_firebird):
        stub_firebird(
            baseline=22788.0,
            daily=[(_day("2026-08-03"), 19820.0, 0.0, 14000.0, 6)],
        )
        res = FirebirdService().get_daily_cash_balances(21066, _day("2026-08-03"), _day("2026-08-03"))
        row = res["days"][0]
        assert row["closing"] == pytest.approx(
            row["opening"] + row["income"] - row["expense"] - row["collection"]
        )
        assert row["closing"] == 28608.0


class TestClamping:
    def test_range_wider_than_the_cap_is_trimmed_from_the_start(self, stub_firebird):
        stub_firebird(baseline=0.0, daily=[])
        res = FirebirdService().get_daily_cash_balances(21066, _day("2013-01-01"), _day("2026-08-05"))

        assert res["clamped"] is True
        assert len(res["days"]) == fb.DAILY_BALANCE_MAX_DAYS
        # The recent end is what's kept — the far past is what gets dropped.
        assert res["date_to"] == "2026-08-05"
        assert res["date_from"] == "2025-08-05"

    def test_range_at_the_cap_is_not_clamped(self, stub_firebird):
        stub_firebird(baseline=0.0, daily=[])
        end = _day("2026-08-05")
        start = end - dt.timedelta(days=fb.DAILY_BALANCE_MAX_DAYS - 1)
        res = FirebirdService().get_daily_cash_balances(21066, start, end)
        assert res["clamped"] is False
        assert len(res["days"]) == fb.DAILY_BALANCE_MAX_DAYS


class TestEntries:
    def test_entry_fields_are_normalized(self, stub_firebird):
        stub_firebird(
            baseline=0.0,
            daily=[(_day("2026-08-01"), 2500.0, 0.0, 0.0, 1)],
            entries=[(
                _day("2026-08-01"), dt.time(16, 45, 12), " 00459 ",
                "Оплата по заказу № 37065-7", 11317,
                10725995, 0, "Реализация (розница) ", 2500.0, 0.0,
            )],
        )
        res = FirebirdService().get_daily_cash_balances(21066, _day("2026-08-01"), _day("2026-08-01"))
        entry = res["entries"][0]

        assert entry["date"] == "2026-08-01"
        assert entry["time"] == "16:45"
        assert entry["doc_num"] == "00459"
        assert entry["basis_name"] == "Реализация (розница)"
        assert entry["basis_text"] == "Оплата по заказу № 37065-7"
        assert entry["debet"] == 2500.0
        assert entry["kredit"] == 0.0
        # Kept as a string: it's matched against employee external_code,
        # which is a string map on the API side.
        assert entry["user_id"] == "11317"

    def test_missing_basis_dictionary_row_does_not_blow_up(self, stub_firebird):
        stub_firebird(
            baseline=0.0,
            daily=[(_day("2026-08-01"), 100.0, 0.0, 0.0, 1)],
            entries=[(_day("2026-08-01"), None, None, None, None, 1, 999, None, 100.0, 0.0)],
        )
        res = FirebirdService().get_daily_cash_balances(21066, _day("2026-08-01"), _day("2026-08-01"))
        entry = res["entries"][0]
        assert entry["time"] == ""
        assert entry["basis_name"] == ""
        assert entry["user_id"] == ""


class TestFailureModes:
    def test_returns_empty_shape_when_driver_missing(self, monkeypatch):
        monkeypatch.setattr(fb, "FIREBIRD_AVAILABLE", False)
        res = FirebirdService().get_daily_cash_balances(21066, _day("2026-08-01"), _day("2026-08-02"))
        assert res["days"] == []
        assert res["entries"] == []
        assert res["opening"] == 0.0

    def test_query_error_returns_empty_shape_not_an_exception(self, monkeypatch):
        monkeypatch.setattr(fb, "FIREBIRD_AVAILABLE", True)

        def boom(*a, **k):
            raise RuntimeError("connection refused")

        monkeypatch.setattr(fb, "_connect", boom)
        res = FirebirdService().get_daily_cash_balances(21066, _day("2026-08-01"), _day("2026-08-02"))
        assert res["days"] == []
        assert res["kassa_id"] == 21066

    def test_connection_is_closed(self, stub_firebird):
        stub_firebird(baseline=0.0, daily=[])
        FirebirdService().get_daily_cash_balances(21066, _day("2026-08-01"), _day("2026-08-01"))
        assert stub_firebird.holder["conn"].closed is True


class TestKassaName:
    def test_stale_agbis_name_is_overridden(self, stub_firebird):
        stub_firebird(baseline=0.0, daily=[], kassa_name="5_Пассаж")
        res = FirebirdService().get_daily_cash_balances(21066, _day("2026-08-01"), _day("2026-08-01"))
        assert res["kassa_name"] == "5_Гранд Палас"

    def test_other_registers_keep_their_agbis_name(self, stub_firebird):
        stub_firebird(baseline=0.0, daily=[], kassa_name="1_Озерки")
        res = FirebirdService().get_daily_cash_balances(21057, _day("2026-08-01"), _day("2026-08-01"))
        assert res["kassa_name"] == "1_Озерки"
