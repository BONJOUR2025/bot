"""AI spend visibility for Настройки → Автоматизация: account-wide totals
live from Polza's own API, plus a locally-logged per-employee breakdown.

Two different data sources, and deliberately not merged into one:

- get_usage_summary/get_polza_balance: GET /v1/history/generations and
  /v1/balance — the account-wide truth, live from Polza, no local copy kept.
  That endpoint already reflects everything billed to the key, better than a
  local mirror could (see https://polza.ai/docs/osobennosti/usage.md).
- record_employee_usage/get_usage_by_employee: local log in EmployeeLlmUsage.
  Polza has no notion of "which employee" made a call — that's our data, not
  theirs — so per-employee attribution can only come from logging it
  ourselves at the moment of the call. See app/models/llm_usage.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func


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


def _session():
    from app.db.session import SessionLocal

    return SessionLocal()


def record_employee_usage(
    *, employee_id: str, employee_name: str, feature: str, provider: str, model: str,
    prompt_tokens: int, completion_tokens: int, total_tokens: int, cost_rub: Optional[float],
    cached_tokens: int = 0,
) -> None:
    from app.models.llm_usage import EmployeeLlmUsage

    db = _session()
    try:
        db.add(EmployeeLlmUsage(
            employee_id=employee_id,
            employee_name=employee_name or "",
            feature=feature or "",
            provider=provider or "",
            model=model or "",
            prompt_tokens=prompt_tokens or 0,
            completion_tokens=completion_tokens or 0,
            total_tokens=total_tokens or 0,
            cached_tokens=cached_tokens or 0,
            cost_rub=cost_rub,
        ))
        db.commit()
    finally:
        db.close()


def get_usage_by_employee(since: Optional[datetime] = None, feature: Optional[str] = None) -> list[dict]:
    """Per-employee totals, most expensive first. This is real-time in the
    sense that it reads whatever has been logged up to this instant — there
    is no batching/aggregation delay, each call writes its row immediately."""
    from app.models.llm_usage import EmployeeLlmUsage

    db = _session()
    try:
        q = db.query(
            EmployeeLlmUsage.employee_id,
            # MAX() rather than grouping by name too: an employee's display
            # name can change between calls (renamed in user.json), and we
            # want one row per employee_id showing their current name, not
            # one row per (id, name) combination fragmenting their history.
            func.max(EmployeeLlmUsage.employee_name),
            func.count(EmployeeLlmUsage.id),
            func.coalesce(func.sum(EmployeeLlmUsage.total_tokens), 0),
            func.coalesce(func.sum(EmployeeLlmUsage.cost_rub), 0.0),
            func.max(EmployeeLlmUsage.created_at),
            func.coalesce(func.sum(EmployeeLlmUsage.cached_tokens), 0),
        ).group_by(EmployeeLlmUsage.employee_id)
        if since is not None:
            q = q.filter(EmployeeLlmUsage.created_at >= since)
        if feature is not None:
            q = q.filter(EmployeeLlmUsage.feature == feature)
        q = q.order_by(func.coalesce(func.sum(EmployeeLlmUsage.cost_rub), 0.0).desc())

        return [
            {
                "employee_id": employee_id,
                "employee_name": employee_name or "",
                "requests": int(requests),
                "tokens": int(tokens),
                "cost_rub": round(float(cost_rub), 4),
                "last_used_at": last_used_at.isoformat() if last_used_at else None,
                "cached_tokens": int(cached_tokens),
            }
            for (employee_id, employee_name, requests, tokens, cost_rub,
                 last_used_at, cached_tokens) in q.all()
        ]
    finally:
        db.close()
