"""Tests for the provider-dispatching LLM abstraction (app/services/llm_client.py).

cfg["llm_provider"] selects "anthropic" (default) or "polza" (the
OpenAI-Chat-Completions-shaped, ruble-billed gateway at polza.ai, used here
to reach DeepSeek). Both get_client() and chat() must dispatch correctly,
and get_client() must stay a pure truthiness check for every other caller
in the codebase that just does `if not get_client(cfg)`.
"""
from __future__ import annotations

import httpx
import pytest

from app.services import llm_client as llm


class _FakeMessages:
    def __init__(self, response_text):
        self._response_text = response_text
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs

        class _Block:
            def __init__(self, text):
                self.text = text

        class _Resp:
            pass

        resp = _Resp()
        resp.content = [_Block(self._response_text)]
        return resp


class _FakeAnthropicClient:
    def __init__(self, api_key=None, http_client=None):
        self.api_key = api_key
        self.messages = _FakeMessages("  привет  ")


class TestProviderDefault:
    def test_defaults_to_anthropic_when_unset(self):
        assert llm._provider({}) == "anthropic"

    def test_is_case_insensitive_and_trims(self):
        assert llm._provider({"llm_provider": "  POLZA  "}) == "polza"


class TestGetClientAnthropic:
    def test_returns_none_without_api_key(self):
        assert llm.get_client({}) is None

    def test_returns_client_with_api_key(self, monkeypatch):
        monkeypatch.setattr("anthropic.Anthropic", _FakeAnthropicClient)
        client = llm.get_client({"anthropic_api_key": "sk-ant-test"})
        assert isinstance(client, _FakeAnthropicClient)
        assert client.api_key == "sk-ant-test"


class TestGetClientPolza:
    def test_returns_none_without_api_key(self):
        assert llm.get_client({"llm_provider": "polza"}) is None

    def test_returns_truthy_with_api_key(self):
        assert llm.get_client({"llm_provider": "polza", "polza_api_key": "pz-test"})


class TestChatAnthropic:
    def test_no_api_key_returns_none(self):
        assert llm.chat({}, [{"role": "user", "content": "hi"}]) is None

    def test_sends_default_model_and_strips_response(self, monkeypatch):
        monkeypatch.setattr("anthropic.Anthropic", _FakeAnthropicClient)
        cfg = {"anthropic_api_key": "sk-ant-test"}
        result = llm.chat(cfg, [{"role": "user", "content": "hi"}])
        assert result == "привет"

    def test_model_override_and_cache_control_applied(self, monkeypatch):
        captured = {}

        class _Capturing(_FakeAnthropicClient):
            def __init__(self, **kw):
                super().__init__(**kw)
                orig_create = self.messages.create

                def create(**kwargs):
                    captured.update(kwargs)
                    return orig_create(**kwargs)

                self.messages.create = create

        monkeypatch.setattr("anthropic.Anthropic", _Capturing)
        cfg = {"anthropic_api_key": "sk-ant-test"}
        llm.chat(cfg, [{"role": "user", "content": "hi"}], system="be nice",
                  model="claude-opus-4-7", max_tokens=42)
        assert captured["model"] == "claude-opus-4-7"
        assert captured["max_tokens"] == 42
        assert captured["system"][0]["cache_control"] == {"type": "ephemeral"}

    def test_cache_system_false_sends_plain_string_system(self, monkeypatch):
        captured = {}

        class _Capturing(_FakeAnthropicClient):
            def __init__(self, **kw):
                super().__init__(**kw)
                orig_create = self.messages.create

                def create(**kwargs):
                    captured.update(kwargs)
                    return orig_create(**kwargs)

                self.messages.create = create

        monkeypatch.setattr("anthropic.Anthropic", _Capturing)
        cfg = {"anthropic_api_key": "sk-ant-test"}
        llm.chat(cfg, [{"role": "user", "content": "hi"}], system="be nice", cache_system=False)
        assert captured["system"] == "be nice"


class TestChatPolza:
    BASE = {"llm_provider": "polza", "polza_api_key": "pz-test"}

    def test_no_api_key_returns_none(self):
        assert llm.chat({"llm_provider": "polza"}, [{"role": "user", "content": "hi"}]) is None

    def test_sends_default_model_and_url_and_parses_response(self, monkeypatch):
        captured = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "  привет от deepseek  "}}]},
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        result = llm.chat(self.BASE, [{"role": "user", "content": "hi"}])

        assert result == "привет от deepseek"
        assert captured["url"] == "https://polza.ai/api/v1/chat/completions"
        assert captured["json"]["model"] == "deepseek/deepseek-chat"
        assert captured["headers"]["Authorization"] == "Bearer pz-test"

    def test_system_prompt_is_prepended_as_message(self, monkeypatch):
        captured = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["json"] = json
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "ok"}}]},
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        llm.chat(self.BASE, [{"role": "user", "content": "hi"}], system="be nice")

        assert captured["json"]["messages"][0] == {"role": "system", "content": "be nice"}
        assert captured["json"]["messages"][1] == {"role": "user", "content": "hi"}

    def test_explicit_model_overrides_configured_default(self, monkeypatch):
        captured = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["json"] = json
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "ok"}}]},
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        cfg = {**self.BASE, "polza_model": "deepseek/deepseek-r1"}
        llm.chat(cfg, [{"role": "user", "content": "hi"}], model="openai/gpt-4o")

        assert captured["json"]["model"] == "openai/gpt-4o"

    def test_configured_polza_model_used_when_no_override(self, monkeypatch):
        captured = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["json"] = json
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "ok"}}]},
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        cfg = {**self.BASE, "polza_model": "deepseek/deepseek-r1"}
        llm.chat(cfg, [{"role": "user", "content": "hi"}])

        assert captured["json"]["model"] == "deepseek/deepseek-r1"

    def test_custom_base_url_is_respected(self, monkeypatch):
        captured = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["url"] = url
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "ok"}}]},
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        cfg = {**self.BASE, "polza_base_url": "https://polza.ai/api/v1/"}
        llm.chat(cfg, [{"role": "user", "content": "hi"}])

        assert captured["url"] == "https://polza.ai/api/v1/chat/completions"

    def test_http_error_status_raises(self, monkeypatch):
        def fake_post(url, json=None, headers=None, timeout=None):
            return httpx.Response(
                401, json={"error": "invalid key"}, request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        with pytest.raises(httpx.HTTPStatusError):
            llm.chat(self.BASE, [{"role": "user", "content": "hi"}])

