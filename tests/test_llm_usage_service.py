"""Tests for the AI spend view in Настройки → Автоматизация.

The account-wide summary (TestGetUsageSummary/TestGetPolzaBalance) has no
local storage of its own — every number comes live from Polza.ai's own API
(GET /v1/history/generations for tokens/cost, GET /v1/balance for remaining
rubles), since that already reflects everything billed to the key, including
calls made outside llm_client.chat().

The per-employee breakdown (TestEmployeeUsage) is the opposite: Polza has no
notion of "which employee" made a call, so that data only ever exists in the
local EmployeeLlmUsage log — these tests point it at a throwaway SQLite file.
"""
from __future__ import annotations

import datetime as dt

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.llm_usage import EmployeeLlmUsage  # noqa: F401 — registers the table
from app.services import llm_usage_service as svc


def _page(items, page=1, total_pages=1):
    return {"items": items, "meta": {"page": page, "limit": 100, "total": len(items), "totalPages": total_pages}}


def _item(tokens, cost):
    return {"usage": {"total_tokens": tokens}, "cost": str(cost)}


class TestGetUsageSummary:
    def test_no_api_key_returns_zeroed_shape(self):
        result = svc.get_usage_summary({})
        assert result == {
            "today": {"requests": 0, "tokens": 0, "cost_rub": 0.0, "truncated": False},
            "period_30d": {"requests": 0, "tokens": 0, "cost_rub": 0.0, "truncated": False},
        }

    def test_single_page_is_summed(self, monkeypatch):
        def fake_get(url, params=None, headers=None, timeout=None):
            assert url == "https://polza.ai/api/v1/history/generations"
            assert headers["Authorization"] == "Bearer pz-test"
            return httpx.Response(200, json=_page([_item(100, "0.01"), _item(50, "0.005")]),
                                   request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)
        result = svc.get_usage_summary({"polza_api_key": "pz-test"})
        assert result["today"] == {"requests": 2, "tokens": 150, "cost_rub": 0.015, "truncated": False}

    def test_date_from_is_sent_for_today_but_not_needed_for_period(self, monkeypatch):
        captured = []

        def fake_get(url, params=None, headers=None, timeout=None):
            captured.append(dict(params))
            return httpx.Response(200, json=_page([]), request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)
        svc.get_usage_summary({"polza_api_key": "pz-test"})

        assert all("dateFrom" in p for p in captured)
        today_call, period_call = captured[0], captured[1]
        assert today_call["dateFrom"] > period_call["dateFrom"]

    def test_pagination_across_pages_is_summed(self, monkeypatch):
        pages = {
            1: _page([_item(10, "0.001")], page=1, total_pages=2),
            2: _page([_item(20, "0.002")], page=2, total_pages=2),
        }

        def fake_get(url, params=None, headers=None, timeout=None):
            return httpx.Response(200, json=pages[params["page"]], request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)
        result = svc.get_usage_summary({"polza_api_key": "pz-test"})
        assert result["today"] == {"requests": 2, "tokens": 30, "cost_rub": 0.003, "truncated": False}

    def test_truncated_when_more_pages_exist_than_max_pages(self, monkeypatch):
        def fake_get(url, params=None, headers=None, timeout=None):
            # totalPages far beyond max_pages — every page looks identical
            return httpx.Response(200, json=_page([_item(1, "0.0001")], page=params["page"], total_pages=999),
                                   request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)
        result = svc._fetch_period_totals({"polza_api_key": "pz-test"}, None, max_pages=3)
        assert result["truncated"] is True
        assert result["requests"] == 3

    def test_missing_usage_or_cost_fields_default_to_zero(self, monkeypatch):
        def fake_get(url, params=None, headers=None, timeout=None):
            return httpx.Response(200, json=_page([{}]), request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)
        result = svc._fetch_period_totals({"polza_api_key": "pz-test"}, None)
        assert result == {"requests": 1, "tokens": 0, "cost_rub": 0.0, "truncated": False}


class TestGetPolzaBalance:
    def test_returns_none_without_api_key(self):
        assert svc.get_polza_balance({}) is None

    def test_returns_parsed_amount(self, monkeypatch):
        def fake_get(url, headers=None, timeout=None):
            assert url == "https://polza.ai/api/v1/balance"
            assert headers["Authorization"] == "Bearer pz-test"
            return httpx.Response(200, json={"amount": "1250.50"}, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)
        assert svc.get_polza_balance({"polza_api_key": "pz-test"}) == 1250.50

    def test_http_error_raises(self, monkeypatch):
        def fake_get(url, headers=None, timeout=None):
            return httpx.Response(401, json={"error": "bad key"}, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)
        with pytest.raises(httpx.HTTPStatusError):
            svc.get_polza_balance({"polza_api_key": "pz-bad"})

    def test_custom_base_url_is_respected(self, monkeypatch):
        captured = {}

        def fake_get(url, headers=None, timeout=None):
            captured["url"] = url
            return httpx.Response(200, json={"amount": "5"}, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)
        svc.get_polza_balance({"polza_api_key": "pz-test", "polza_base_url": "https://polza.ai/api/v1/"})
        assert captured["url"] == "https://polza.ai/api/v1/balance"


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine, tables=[EmployeeLlmUsage.__table__])
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(svc, "_session", lambda: Session())
    yield
    engine.dispose()


def _log(employee_id, employee_name="", feature="knowledge_base", provider="polza",
         model="deepseek/deepseek-chat", prompt_tokens=10, completion_tokens=20,
         total_tokens=30, cost_rub=1.5, cached_tokens=0):
    svc.record_employee_usage(
        employee_id=employee_id, employee_name=employee_name, feature=feature,
        provider=provider, model=model, prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens, total_tokens=total_tokens, cost_rub=cost_rub,
        cached_tokens=cached_tokens,
    )


class TestEmployeeUsage:
    def test_record_and_fetch_single_employee(self, temp_db):
        _log("1", "Анастасия")

        rows = svc.get_usage_by_employee()

        assert len(rows) == 1
        assert rows[0]["employee_id"] == "1"
        assert rows[0]["employee_name"] == "Анастасия"
        assert rows[0]["requests"] == 1
        assert rows[0]["tokens"] == 30
        assert rows[0]["cost_rub"] == 1.5
        assert rows[0]["last_used_at"] is not None

    def test_multiple_calls_aggregate_per_employee(self, temp_db):
        _log("1", "Анастасия", total_tokens=30, cost_rub=1.5)
        _log("1", "Анастасия", total_tokens=50, cost_rub=2.5)
        _log("2", "Вера", total_tokens=10, cost_rub=0.5)

        rows = {r["employee_id"]: r for r in svc.get_usage_by_employee()}

        assert rows["1"]["requests"] == 2
        assert rows["1"]["tokens"] == 80
        assert rows["1"]["cost_rub"] == 4.0
        assert rows["2"]["requests"] == 1

    def test_ordered_most_expensive_first(self, temp_db):
        _log("1", "Дешёвый", cost_rub=0.5)
        _log("2", "Дорогой", cost_rub=9.0)

        rows = svc.get_usage_by_employee()

        assert [r["employee_id"] for r in rows] == ["2", "1"]

    def test_feature_filter(self, temp_db):
        _log("1", "Анастасия", feature="knowledge_base")
        _log("1", "Анастасия", feature="other_feature")

        kb_rows = svc.get_usage_by_employee(feature="knowledge_base")

        assert len(kb_rows) == 1
        assert kb_rows[0]["requests"] == 1

    def test_since_filter_excludes_old_rows(self, temp_db):
        db = svc._session()
        try:
            db.add(EmployeeLlmUsage(
                employee_id="1", employee_name="Старый", feature="knowledge_base",
                provider="polza", model="x", prompt_tokens=1, completion_tokens=1,
                total_tokens=2, cost_rub=1.0,
                created_at=dt.datetime.utcnow() - dt.timedelta(days=60),
            ))
            db.commit()
        finally:
            db.close()

        _log("2", "Новый")

        rows = svc.get_usage_by_employee(since=dt.datetime.utcnow() - dt.timedelta(days=30))

        assert len(rows) == 1
        assert rows[0]["employee_id"] == "2"

    def test_anthropic_rows_have_no_cost(self, temp_db):
        _log("1", "Анастасия", provider="anthropic", cost_rub=None)

        rows = svc.get_usage_by_employee()

        assert rows[0]["cost_rub"] == 0.0

    def test_no_usage_returns_empty_list(self, temp_db):
        assert svc.get_usage_by_employee() == []

    def test_cached_tokens_are_summed(self, temp_db):
        _log("1", "Анастасия", total_tokens=50000, cached_tokens=47616)
        _log("1", "Анастасия", total_tokens=50000, cached_tokens=47616)

        rows = svc.get_usage_by_employee()

        assert rows[0]["cached_tokens"] == 95232

    def test_uncached_rows_report_zero_not_null(self, temp_db):
        """A model whose provider has no prompt cache reports nothing at all,
        not a zero — the column must still read back as 0 so the UI can show
        an honest "0%" rather than a blank."""
        _log("1", "Анастасия", cached_tokens=0)

        assert svc.get_usage_by_employee()[0]["cached_tokens"] == 0
