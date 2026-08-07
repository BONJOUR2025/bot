"""Tracks LLM token/ruble spend for the live usage view in Настройки → Автоматизация.

Two independent numbers are shown, deliberately not merged into one:
- our own running log (get_usage_summary) — built from the `usage` object
  Polza returns on every response (https://polza.ai/docs/osobennosti/usage.md),
  recorded as a side effect of llm_client._chat_polza. This is only as
  complete as our own logging — it won't reflect spend from outside this app.
- Polza's own account balance (get_polza_balance) — a live call to their
  GET /v1/balance endpoint, the authoritative remaining-rubles number.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import func

log = logging.getLogger(__name__)


def _session():
    from app.db.session import SessionLocal

    return SessionLocal()


def record_usage(*, provider: str, model: str, prompt_tokens: int, completion_tokens: int,
                  total_tokens: int, cost_rub: Optional[float]) -> None:
    from app.models.llm_usage import LlmUsageLog

    db = _session()
    try:
        db.add(LlmUsageLog(
            provider=provider,
            model=model or "",
            prompt_tokens=prompt_tokens or 0,
            completion_tokens=completion_tokens or 0,
            total_tokens=total_tokens or 0,
            cost_rub=cost_rub,
        ))
        db.commit()
    finally:
        db.close()


def _summarize(db, LlmUsageLog, since: Optional[datetime]) -> dict:
    q = db.query(
        func.count(LlmUsageLog.id),
        func.coalesce(func.sum(LlmUsageLog.total_tokens), 0),
        func.coalesce(func.sum(LlmUsageLog.cost_rub), 0.0),
    )
    if since is not None:
        q = q.filter(LlmUsageLog.created_at >= since)
    requests, tokens, cost_rub = q.one()
    return {"requests": int(requests), "tokens": int(tokens), "cost_rub": round(float(cost_rub), 4)}


def get_usage_summary() -> dict:
    """Returns {"today": {requests, tokens, cost_rub}, "total": {...}}."""
    from app.models.llm_usage import LlmUsageLog

    db = _session()
    try:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return {
            "today": _summarize(db, LlmUsageLog, today_start),
            "total": _summarize(db, LlmUsageLog, None),
        }
    finally:
        db.close()


def get_polza_balance(cfg: dict) -> Optional[float]:
    """Live remaining balance in rubles from Polza's own API. Returns None
    if no key is configured; raises on a request/parse failure so the
    caller can distinguish "not configured" from "API error"."""
    api_key = (cfg.get("polza_api_key") or "").strip()
    if not api_key:
        return None

    import httpx
    base_url = (cfg.get("polza_base_url") or "https://polza.ai/api/v1").rstrip("/")
    response = httpx.get(
        f"{base_url}/balance",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15.0,
    )
    response.raise_for_status()
    return float(response.json()["amount"])
