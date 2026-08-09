"""The knowledge-base bot answers on its own model, separate from the
account-wide polza_model.

Why this is worth a test rather than a one-line default: the KB resends the
whole knowledge base (~50k tokens) with every single question, so the only
thing that meaningfully moves the bill is whether the provider serves that
prefix from its prompt cache. Measured against the real KB through Polza,
deepseek/deepseek-chat returns cached_tokens=0 on every repeat (Polza routes
it to third-party hosts with no prefix cache; pinning the real DeepSeek
provider returns 503) at ~1.58₽ a question, while openai/gpt-4.1-nano serves
~47.6k tokens from cache for ~0.14₽.

The separation matters in both directions: polza_model also drives the
candidate-facing recruitment AI, which must not change as a side effect, and
DEFAULT_KB_MODEL is a Polza-style "provider/model" id that the Anthropic SDK
would reject outright.
"""
from __future__ import annotations

from app.handlers.knowledge_base import DEFAULT_KB_MODEL, _kb_model


class TestKbModelSelection:
    def test_polza_provider_gets_the_cache_capable_default(self):
        assert _kb_model({"llm_provider": "polza"}) == DEFAULT_KB_MODEL

    def test_default_is_not_the_account_wide_polza_model(self):
        """Setting polza_model must not drag the KB along with it — that field
        is what the recruitment AI talks to candidates on."""
        cfg = {"llm_provider": "polza", "polza_model": "deepseek/deepseek-chat"}
        assert _kb_model(cfg) == DEFAULT_KB_MODEL
        assert _kb_model(cfg) != cfg["polza_model"]

    def test_anthropic_provider_gets_no_override(self):
        """A "provider/model" id would fail against the Anthropic SDK, so the
        KB falls back to whatever llm_client picks for that provider."""
        assert _kb_model({"llm_provider": "anthropic"}) is None
        assert _kb_model({}) is None

    def test_explicit_kb_model_wins_on_either_provider(self):
        assert _kb_model({"llm_provider": "polza", "kb_model": "openai/gpt-5-nano"}) == "openai/gpt-5-nano"
        assert _kb_model(
            {"llm_provider": "anthropic", "kb_model": "claude-haiku-4-5-20251001"}
        ) == "claude-haiku-4-5-20251001"

    def test_blank_and_whitespace_kb_model_fall_back_to_default(self):
        assert _kb_model({"llm_provider": "polza", "kb_model": ""}) == DEFAULT_KB_MODEL
        assert _kb_model({"llm_provider": "polza", "kb_model": "   "}) == DEFAULT_KB_MODEL

    def test_explicit_model_is_trimmed(self):
        assert _kb_model({"llm_provider": "polza", "kb_model": "  openai/gpt-4.1-nano  "}) == "openai/gpt-4.1-nano"

    def test_provider_matching_is_case_insensitive(self):
        assert _kb_model({"llm_provider": "  POLZA "}) == DEFAULT_KB_MODEL
