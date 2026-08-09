"""Single-point LLM abstraction. To swap providers change only this file.

Two providers are supported, selected by cfg["llm_provider"] ("anthropic",
the default, or "polza"):

- anthropic: calls the Anthropic API directly via the official SDK.
- polza: calls Polza.ai (https://polza.ai/docs) — an OpenAI-Chat-Completions
  -shaped gateway billed in rubles, giving access to many providers'
  models (incl. DeepSeek) under model ids of the form "provider/model",
  e.g. "deepseek/deepseek-chat". Verify the exact live model id in the
  Polza dashboard/catalog before relying on the default below — their
  docs were inconsistent about whether ids are provider-prefixed.

cache_system (prompt caching via cache_control) is an Anthropic-specific
mechanism and has no effect on the polza path — it is silently ignored
there rather than erroring, so callers don't need to branch on provider.
"""
import logging
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_POLZA_MODEL = "deepseek/deepseek-chat"
DEFAULT_POLZA_BASE_URL = "https://polza.ai/api/v1"


def _provider(cfg: dict) -> str:
    return (cfg.get("llm_provider") or "anthropic").strip().lower()


def get_client(cfg: dict):
    """Return a truthy value if the configured provider is ready to use,
    else None. For "anthropic" this is a real, usable Anthropic SDK client
    (kept, since some callers may want it directly); for "polza" there is
    no SDK client object, so this returns the (truthy) API key instead —
    callers only ever use the return value in a boolean context."""
    if _provider(cfg) == "polza":
        return (cfg.get("polza_api_key") or "").strip() or None

    api_key = (cfg.get("anthropic_api_key") or "").strip() or None
    if not api_key:
        return None

    proxy_url = None
    try:
        from app.settings import settings as _s
        proxy_url = getattr(_s, "telegram_proxy", None)
    except Exception:
        pass

    http_client = None
    if proxy_url:
        import httpx
        http_client = httpx.Client(proxy=proxy_url)

    from anthropic import Anthropic
    return Anthropic(api_key=api_key, http_client=http_client)


def chat(
    cfg: dict,
    messages: list,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 256,
    cache_system: bool = True,
    employee_id: Optional[str] = None,
    employee_name: Optional[str] = None,
    feature: Optional[str] = None,
) -> Optional[str]:
    """
    Send a chat request and return the text response, or None if unavailable.

    Args:
        cfg:        config dict (must contain anthropic_api_key, or
                    polza_api_key when cfg["llm_provider"] == "polza")
        messages:   list of {"role": "user"/"assistant", "content": "..."}
        system:     optional system prompt
        model:      model override; defaults to DEFAULT_MODEL (anthropic) or
                    cfg["polza_model"]/DEFAULT_POLZA_MODEL (polza)
        max_tokens: max tokens in the response
        cache_system: if True, mark the system prompt with cache_control so the
                    knowledge-base block (large and unchanged within a dialogue)
                    is billed at the discounted cached-input rate on repeat
                    turns within the cache window, instead of full price each
                    time. No effect on the response itself. Anthropic-only;
                    ignored on the polza path.
        employee_id: pass together with feature to attribute this call's
                    token/cost usage to a specific employee (e.g. the
                    Telegram-bot knowledge base) — see
                    app/services/llm_usage_service.py. Omit for calls that
                    aren't tied to one employee (candidate interviews,
                    briefings, admin tools); this account-wide usage is
                    already visible live via Polza's own history endpoint.
        employee_name: display name for the same log row; purely cosmetic.
        feature:    short tag identifying which feature made the call, e.g.
                    "knowledge_base" — lets usage be filtered per feature.
    """
    attribution = (
        {"employee_id": employee_id, "employee_name": employee_name or "", "feature": feature or ""}
        if employee_id else None
    )
    if _provider(cfg) == "polza":
        return _chat_polza(cfg, messages, system=system, model=model, max_tokens=max_tokens,
                            attribution=attribution)
    return _chat_anthropic(cfg, messages, system=system, model=model, max_tokens=max_tokens,
                            cache_system=cache_system, attribution=attribution)


def _record_usage_safely(attribution: Optional[dict], *, provider: str, model: str,
                          prompt_tokens: int, completion_tokens: int, total_tokens: int,
                          cost_rub: Optional[float]) -> None:
    """Best-effort: a logging failure must never break an actual chat reply."""
    if not attribution:
        return
    try:
        from app.services.llm_usage_service import record_employee_usage
        record_employee_usage(
            employee_id=attribution["employee_id"],
            employee_name=attribution.get("employee_name") or "",
            feature=attribution.get("feature") or "",
            provider=provider, model=model or "",
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            total_tokens=total_tokens, cost_rub=cost_rub,
        )
    except Exception:
        log.warning("llm_client: failed to record per-employee usage", exc_info=True)


def _chat_anthropic(
    cfg: dict, messages: list, *, system: Optional[str], model: Optional[str],
    max_tokens: int, cache_system: bool, attribution: Optional[dict] = None,
) -> Optional[str]:
    client = get_client(cfg)
    if not client:
        log.warning("llm_client: no Anthropic API key configured")
        return None

    resolved_model = model or DEFAULT_MODEL
    kwargs = dict(
        model=resolved_model,
        max_tokens=max_tokens,
        messages=messages,
    )
    if system:
        # Pass the system prompt as a cacheable text block. A single ephemeral
        # cache breakpoint covers the whole prompt prefix, so the bulky,
        # turn-invariant knowledge base is reused from cache instead of being
        # re-tokenised at full price on every incoming candidate message.
        kwargs["system"] = (
            [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
            if cache_system else system
        )

    response = client.messages.create(**kwargs)
    usage = getattr(response, "usage", None)
    # Anthropic reports no ruble cost — cost_rub stays None for these rows,
    # same convention the account-wide log used before it was replaced by a
    # live Polza pull (see llm_usage_service.py's module docstring).
    _record_usage_safely(
        attribution, provider="anthropic", model=resolved_model,
        prompt_tokens=getattr(usage, "input_tokens", 0) or 0,
        completion_tokens=getattr(usage, "output_tokens", 0) or 0,
        total_tokens=(getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "output_tokens", 0) or 0),
        cost_rub=None,
    )
    return response.content[0].text.strip()


def _chat_polza(
    cfg: dict, messages: list, *, system: Optional[str], model: Optional[str], max_tokens: int,
    attribution: Optional[dict] = None,
) -> Optional[str]:
    api_key = (cfg.get("polza_api_key") or "").strip()
    if not api_key:
        log.warning("llm_client: no Polza API key configured")
        return None

    import httpx

    base_url = (cfg.get("polza_base_url") or DEFAULT_POLZA_BASE_URL).rstrip("/")
    payload_messages = list(messages)
    if system:
        payload_messages = [{"role": "system", "content": system}] + payload_messages

    resolved_model = model or (cfg.get("polza_model") or "").strip() or DEFAULT_POLZA_MODEL
    body = {
        "model": resolved_model,
        "messages": payload_messages,
        "max_tokens": max_tokens,
    }
    response = httpx.post(
        f"{base_url}/chat/completions",
        json=body,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()
    usage = data.get("usage") or {}
    _record_usage_safely(
        attribution, provider="polza", model=data.get("model") or resolved_model,
        prompt_tokens=usage.get("prompt_tokens") or 0,
        completion_tokens=usage.get("completion_tokens") or 0,
        total_tokens=usage.get("total_tokens") or 0,
        cost_rub=usage.get("cost_rub"),
    )
    return data["choices"][0]["message"]["content"].strip()
