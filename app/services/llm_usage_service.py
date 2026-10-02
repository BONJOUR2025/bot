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


# Cap on the stored question/answer text. Long enough that a knowledge-base
# exchange is kept whole (the handler caps answers at 600 tokens), short
# enough that a runaway paste can't bloat hr.db, which the bot and API share.
MAX_TEXT_CHARS = 4000


def _truncate(text: Optional[str]) -> str:
    text = (text or "").strip()
    if len(text) <= MAX_TEXT_CHARS:
        return text
    return text[:MAX_TEXT_CHARS] + "…"


def _session():
    from app.db.session import SessionLocal

    return SessionLocal()


def record_employee_usage(
    *, employee_id: str, employee_name: str, feature: str, provider: str, model: str,
    prompt_tokens: int, completion_tokens: int, total_tokens: int, cost_rub: Optional[float],
    cached_tokens: int = 0, question: Optional[str] = None, answer: Optional[str] = None,
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
            question=_truncate(question),
            answer=_truncate(answer),
        ))
        db.commit()
    finally:
        db.close()


def get_employee_usage_details(employee_id: str, *, since: Optional[datetime] = None,
                                feature: Optional[str] = None, limit: int = 200) -> list[dict]:
    """Individual requests for one employee, newest first — what the per-employee
    totals are actually made of. Rows logged before question/answer were stored
    come back with empty strings rather than being hidden, so the spend history
    stays complete."""
    from app.models.llm_usage import EmployeeLlmUsage

    db = _session()
    try:
        q = db.query(EmployeeLlmUsage).filter(EmployeeLlmUsage.employee_id == str(employee_id))
        if since is not None:
            q = q.filter(EmployeeLlmUsage.created_at >= since)
        if feature is not None:
            q = q.filter(EmployeeLlmUsage.feature == feature)
        rows = q.order_by(EmployeeLlmUsage.created_at.desc()).limit(limit).all()

        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "feature": r.feature or "",
                "provider": r.provider or "",
                "model": r.model or "",
                "prompt_tokens": int(r.prompt_tokens or 0),
                "completion_tokens": int(r.completion_tokens or 0),
                "total_tokens": int(r.total_tokens or 0),
                "cached_tokens": int(r.cached_tokens or 0),
                "cost_rub": round(float(r.cost_rub), 4) if r.cost_rub is not None else None,
                "question": r.question or "",
                "answer": r.answer or "",
            }
            for r in rows
        ]
    finally:
        db.close()


def get_usage_by_employee(since: Optional[datetime] = None, feature: Optional[str] = None,
                          exclude_features: tuple[str, ...] = ()) -> list[dict]:
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
        if exclude_features:
            q = q.filter(~EmployeeLlmUsage.feature.in_(exclude_features))
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


# ── «Помощь» в админке ────────────────────────────────────────────────
HELP_FEATURES = ("admin_help", "admin_help_filter")
# Разрыв между фильтром и ответом на один вопрос — секунды; минута с запасом
# покрывает медленный ответ модели и не склеивает соседние вопросы.
_HELP_PAIR_WINDOW_S = 120


def _is_filter_row(r) -> bool:
    # До разделения меток фильтр тоже писался как admin_help — его ответ
    # всегда одно слово «ДА»/«НЕТ», по нему и отличаем старые строки.
    if r.feature == "admin_help_filter":
        return True
    return (r.answer or "").strip().upper().rstrip(".") in ("ДА", "НЕТ")


def get_help_usage(since: Optional[datetime] = None, recent_limit: int = 50) -> dict:
    """Сколько стоили вопросы к помощнику на странице «Помощь».

    На каждый вопрос — до двух вызовов: фильтр (дёшево, всегда) и ответ
    (только если фильтр пропустил). Здесь они склеиваются обратно в вопросы,
    чтобы цена считалась на вопрос, а не на вызов модели."""
    from app.models.llm_usage import EmployeeLlmUsage

    db = _session()
    try:
        q = db.query(EmployeeLlmUsage).filter(EmployeeLlmUsage.feature.in_(HELP_FEATURES))
        if since is not None:
            q = q.filter(EmployeeLlmUsage.created_at >= since)
        rows = q.order_by(EmployeeLlmUsage.created_at.asc()).all()
    finally:
        db.close()

    questions: list[dict] = []
    open_by_user: dict[str, dict] = {}   # последний вопрос пользователя, ждущий ответа
    for r in rows:
        cost = float(r.cost_rub) if r.cost_rub is not None else 0.0
        tokens = int(r.total_tokens or 0)
        if _is_filter_row(r):
            item = {
                "employee_id": r.employee_id, "employee_name": r.employee_name or r.employee_id,
                "created_at": r.created_at,
                "question": (r.question or "").split("Последний вопрос:\n")[-1].strip(),
                "answer": "", "passed": (r.answer or "").strip().upper().startswith("ДА"),
                "answered": False, "cost_rub": cost, "filter_cost_rub": cost, "tokens": tokens,
            }
            questions.append(item)
            open_by_user[r.employee_id] = item
            continue
        item = open_by_user.pop(r.employee_id, None)
        if (item is None or item["answered"] or not r.created_at or not item["created_at"]
                or (r.created_at - item["created_at"]).total_seconds() > _HELP_PAIR_WINDOW_S):
            # Ответ без своего фильтра — считаем отдельным вопросом, чтобы
            # ни один рубль не потерялся из итога.
            item = {
                "employee_id": r.employee_id, "employee_name": r.employee_name or r.employee_id,
                "created_at": r.created_at, "question": r.question or "", "answer": "",
                "passed": True, "answered": False, "cost_rub": 0.0, "filter_cost_rub": 0.0, "tokens": 0,
            }
            questions.append(item)
        item["answered"] = True
        item["answer"] = r.answer or ""
        item["question"] = r.question or item["question"]
        item["cost_rub"] += cost
        item["tokens"] += tokens

    total_cost = sum(qq["cost_rub"] for qq in questions)
    filter_cost = sum(qq["filter_cost_rub"] for qq in questions)
    answered = sum(1 for qq in questions if qq["answered"])
    by_user: dict[str, dict] = {}
    for qq in questions:
        u = by_user.setdefault(qq["employee_id"], {
            "employee_id": qq["employee_id"], "employee_name": qq["employee_name"],
            "questions": 0, "answered": 0, "rejected": 0, "cost_rub": 0.0, "last_used_at": None,
        })
        u["questions"] += 1
        u["answered" if qq["answered"] else "rejected"] += 1
        u["cost_rub"] += qq["cost_rub"]
        u["last_used_at"] = qq["created_at"]

    def iso(dt):
        return dt.isoformat() if dt else None

    return {
        "questions": len(questions),
        "answered": answered,
        "rejected": len(questions) - answered,
        "cost_rub": round(total_cost, 4),
        "filter_cost_rub": round(filter_cost, 4),
        "answer_cost_rub": round(total_cost - filter_cost, 4),
        "avg_cost_rub": round(total_cost / len(questions), 4) if questions else 0.0,
        "tokens": sum(qq["tokens"] for qq in questions),
        "by_user": sorted(
            ({**u, "cost_rub": round(u["cost_rub"], 4), "last_used_at": iso(u["last_used_at"])} for u in by_user.values()),
            key=lambda u: u["cost_rub"], reverse=True,
        ),
        "recent": [
            {k: (iso(v) if k == "created_at" else round(v, 4) if k in ("cost_rub", "filter_cost_rub") else v)
             for k, v in qq.items()}
            for qq in reversed(questions[-recent_limit:])
        ],
    }
