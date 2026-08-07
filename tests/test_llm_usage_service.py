"""Tests for the AI spend view in Настройки → Автоматизация.

Deliberately has no local storage of its own — every number comes live from
Polza.ai's own API (GET /v1/history/generations for tokens/cost,
GET /v1/balance for remaining rubles), since that already reflects
everything billed to the key, including calls made outside llm_client.chat().
"""
from __future__ import annotations

import httpx
import pytest

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
