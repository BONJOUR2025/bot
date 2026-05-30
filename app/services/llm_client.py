"""Single-point LLM abstraction. To swap providers change only this file."""
import logging
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def get_client(cfg: dict):
    """Return a configured Anthropic client, or None if API key is missing."""
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
) -> Optional[str]:
    """
    Send a chat request and return the text response, or None if unavailable.

    Args:
        cfg:        config dict (must contain anthropic_api_key)
        messages:   list of {"role": "user"/"assistant", "content": "..."}
        system:     optional system prompt
        model:      model override; defaults to DEFAULT_MODEL
        max_tokens: max tokens in the response
    """
    client = get_client(cfg)
    if not client:
        log.warning("llm_client: no API key configured")
        return None

    kwargs = dict(
        model=model or DEFAULT_MODEL,
        max_tokens=max_tokens,
        messages=messages,
    )
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)
    return response.content[0].text.strip()
