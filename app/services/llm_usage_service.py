"""Live AI spend view for Настройки → Автоматизация, sourced directly from
Polza.ai's own API rather than a local log:

- GET /v1/history/generations (dateFrom-filterable, paginated via meta.page/
  meta.totalPages) — per-request history with tokens and cost ("cost" field,
  a decimal string in rubles). This is authoritative: it reflects everything
  billed to the API key, not just calls made through llm_client.chat().
- GET /v1/balance — current remaining balance.

https://polza.ai/docs/osobennosti/usage.md
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


def _base_url(cfg: dict) -> str:
    return (cfg.get("polza_base_url") or "https://polza.ai/api/v1").rstrip("/")


def _fetch_period_totals(cfg: dict, date_from: Optional[datetime], *, max_pages: int = 10,
                          page_size: int = 100) -> dict:
    """Sums tokens/cost/requests over all generations since date_from (or all
    time if None), paginating up to max_pages. truncated=True means older
    entries within the window exist beyond what was summed — a real cap on
    an unbounded loop, not silent data loss for realistic daily volumes."""
    api_key = (cfg.get("polza_api_key") or "").strip()
    if not api_key:
        return {"requests": 0, "tokens": 0, "cost_rub": 0.0, "truncated": False}

    import httpx

    base_url = _base_url(cfg)
    params = {"limit": page_size}
    if date_from is not None:
        params["dateFrom"] = date_from.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    requests_ = tokens = 0
    cost_rub = 0.0
    truncated = False
    for page in range(1, max_pages + 1):
        response = httpx.get(
            f"{base_url}/history/generations",
            params={**params, "page": page},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        items = data.get("items") or []
        for item in items:
            requests_ += 1
            tokens += (item.get("usage") or {}).get("total_tokens") or 0
            cost_rub += float(item.get("cost") or 0)

        total_pages = (data.get("meta") or {}).get("totalPages") or 1
        if page >= total_pages:
            break
        if page == max_pages:
            truncated = True

    return {"requests": requests_, "tokens": tokens, "cost_rub": round(cost_rub, 4), "truncated": truncated}


def get_usage_summary(cfg: dict) -> dict:
    """Returns {"today": {...}, "period_30d": {...}} — both live from Polza,
    not from anything we log ourselves. Empty (all-zero) dicts when no
    Polza key is configured, same shape either way."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    period_start = today_start - timedelta(days=30)
    return {
        "today": _fetch_period_totals(cfg, today_start),
        "period_30d": _fetch_period_totals(cfg, period_start),
    }


def get_polza_balance(cfg: dict) -> Optional[float]:
    """Live remaining balance in rubles from Polza's own API. Returns None
    if no key is configured; raises on a request/parse failure so the
    caller can distinguish "not configured" from "API error"."""
    api_key = (cfg.get("polza_api_key") or "").strip()
    if not api_key:
        return None

    import httpx
    response = httpx.get(
        f"{_base_url(cfg)}/balance",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15.0,
    )
    response.raise_for_status()
    return float(response.json()["amount"])
