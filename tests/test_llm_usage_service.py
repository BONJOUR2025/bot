"""Tests for the AI spend tracker behind the live usage view in Настройки →
Автоматизация. Same throwaway-SQLite pattern as test_fdb_cache.py — no hr.db.
"""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.llm_usage import LlmUsageLog  # noqa: F401 — registers the table
from app.services import llm_usage_service as svc


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine, tables=[LlmUsageLog.__table__])
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(svc, "_session", lambda: Session())
    yield
    engine.dispose()


class TestRecordAndSummarize:
    def test_empty_log_returns_zeroed_summary(self):
        result = svc.get_usage_summary()
        assert result == {
            "today": {"requests": 0, "tokens": 0, "cost_rub": 0.0},
            "total": {"requests": 0, "tokens": 0, "cost_rub": 0.0},
        }

    def test_recorded_usage_is_reflected_in_today_and_total(self):
        svc.record_usage(provider="polza", model="deepseek/deepseek-chat",
                          prompt_tokens=100, completion_tokens=50, total_tokens=150,
                          cost_rub=0.0087)
        result = svc.get_usage_summary()
        for bucket in ("today", "total"):
            assert result[bucket] == {"requests": 1, "tokens": 150, "cost_rub": 0.0087}

    def test_multiple_calls_accumulate(self):
        for _ in range(3):
            svc.record_usage(provider="polza", model="deepseek/deepseek-chat",
                              prompt_tokens=10, completion_tokens=10, total_tokens=20,
                              cost_rub=0.001)
        result = svc.get_usage_summary()
        assert result["total"] == {"requests": 3, "tokens": 60, "cost_rub": 0.003}

    def test_null_cost_rub_does_not_break_sum(self):
        """anthropic-provider rows (no cost_rub) must not poison the sum."""
        svc.record_usage(provider="anthropic", model="claude-haiku-4-5-20251001",
                          prompt_tokens=10, completion_tokens=10, total_tokens=20,
                          cost_rub=None)
        svc.record_usage(provider="polza", model="deepseek/deepseek-chat",
                          prompt_tokens=10, completion_tokens=10, total_tokens=20,
                          cost_rub=0.001)
        result = svc.get_usage_summary()
        assert result["total"] == {"requests": 2, "tokens": 40, "cost_rub": 0.001}


class TestGetPolzaBalance:
    def test_returns_none_without_api_key(self):
        assert svc.get_polza_balance({}) is None

    def test_returns_parsed_amount(self, monkeypatch):
        def fake_get(url, headers=None, timeout=None):
            assert url == "https://polza.ai/api/v1/balance"
            assert headers["Authorization"] == "Bearer pz-test"
            return httpx.Response(200, json={"amount": "1250.50"}, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)
        balance = svc.get_polza_balance({"polza_api_key": "pz-test"})
        assert balance == 1250.50

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
