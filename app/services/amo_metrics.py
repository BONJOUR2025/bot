"""Compute manager KPI metrics from amoCRM for a period.

Attribution (per discussion with the РОП):
  * Denominator of conversion — deals CREATED in the period (created_at), per
    pipeline, by the manager.
  * Numerator of conversion AND revenue — deals that REACHED a target stage
    («Заказ создан» / «Успешно реализовано») DURING the period, by the date of
    the stage transition. This is read from /api/v4/events (lead_status_changed):
    a status-change event inherently means the deal was MOVED onto the stage
    (a deal created directly in a stage produces no such event), so the
    "moved, not created in it" rule is satisfied exactly — no heuristic.
  * sew new leads — deals created in the period in the sew pipeline.

amoCRM is unreachable from this sandbox, so the exact filter-param spellings
must be confirmed against the live account; the logic is unit-tested with stubs.
"""
from __future__ import annotations

from datetime import datetime

from app.services.amo_client import amo_get
from app.services.manager_salary import (
    PIPELINE_REPAIR, PIPELINE_SEW,
    STAGE_ORDER_CREATED_REPAIR, STAGE_ORDER_CREATED_SEW, STAGE_WON,
)

REPAIR_TARGET_STAGES = {STAGE_ORDER_CREATED_REPAIR, STAGE_WON}
SEW_TARGET_STAGES = {STAGE_ORDER_CREATED_SEW, STAGE_WON}


async def _fetch_pipeline_leads(pipeline_id: int, ts_from: int, ts_to: int,
                                amo_user_id: int | None) -> list[dict]:
    """All leads created in the period in a pipeline (conversion denominator)."""
    leads: list[dict] = []
    page = 1
    while True:
        params = {
            "filter[pipeline_id]": pipeline_id,
            "filter[created_at][from]": ts_from,
            "filter[created_at][to]": ts_to,
            "limit": 250,
            "page": page,
        }
        if amo_user_id:
            params["filter[responsible_user_id]"] = amo_user_id
        data = await amo_get("/leads", params=params)
        batch = data.get("_embedded", {}).get("leads", [])
        if not batch:
            break
        leads.extend(batch)
        if len(batch) < 250:
            break
        page += 1
    return leads


def _event_stage(ev: dict) -> tuple[int | None, int | None]:
    """Extract (status_id, pipeline_id) of value_after from a status-change event."""
    after = ev.get("value_after")
    if isinstance(after, list) and after:
        after = after[0]
    if isinstance(after, dict):
        ls = after.get("lead_status") or after
        return ls.get("id"), ls.get("pipeline_id")
    return None, None


async def _leads_reached_target(ts_from: int, ts_to: int) -> dict[int, int]:
    """lead_id -> pipeline_id for leads that reached a target stage in the period
    (read from status-change events)."""
    reached: dict[int, int] = {}
    page = 1
    while True:
        params = {
            "filter[type]": "lead_status_changed",
            "filter[created_at][from]": ts_from,
            "filter[created_at][to]": ts_to,
            "limit": 100,
            "page": page,
        }
        data = await amo_get("/events", params=params)
        batch = data.get("_embedded", {}).get("events", [])
        if not batch:
            break
        for ev in batch:
            sid, pid = _event_stage(ev)
            lead_id = ev.get("entity_id")
            if lead_id is None or sid is None:
                continue
            if pid == PIPELINE_REPAIR and sid in REPAIR_TARGET_STAGES:
                reached[lead_id] = PIPELINE_REPAIR
            elif pid == PIPELINE_SEW and sid in SEW_TARGET_STAGES:
                reached[lead_id] = PIPELINE_SEW
        if len(batch) < 100:
            break
        page += 1
    return reached


async def _fetch_leads_by_ids(ids: list[int]) -> dict[int, dict]:
    """Fetch leads (id -> lead) in chunks, to read responsible_user_id and price."""
    out: dict[int, dict] = {}
    CHUNK = 50
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i:i + CHUNK]
        data = await amo_get("/leads", params={"filter[id][]": chunk, "limit": CHUNK})
        for lead in data.get("_embedded", {}).get("leads", []):
            out[lead.get("id")] = lead
    return out


async def compute_metrics(date_from: datetime, date_to: datetime,
                          amo_user_id: int | None) -> dict:
    ts_from, ts_to = int(date_from.timestamp()), int(date_to.timestamp())

    # Denominators — leads created in the period.
    repair_all = await _fetch_pipeline_leads(PIPELINE_REPAIR, ts_from, ts_to, amo_user_id)
    sew_all = await _fetch_pipeline_leads(PIPELINE_SEW, ts_from, ts_to, amo_user_id)

    # Numerator + revenue — leads that reached a target stage during the period.
    reached = await _leads_reached_target(ts_from, ts_to)
    info = await _fetch_leads_by_ids(list(reached.keys())) if reached else {}

    repair_target = 0
    sew_target = 0
    revenue = 0.0
    for lead_id, pipeline_id in reached.items():
        lead = info.get(lead_id)
        if not lead:
            continue
        if amo_user_id and lead.get("responsible_user_id") != amo_user_id:
            continue
        price = float(lead.get("price") or 0)
        if pipeline_id == PIPELINE_REPAIR:
            repair_target += 1
            revenue += price
        elif pipeline_id == PIPELINE_SEW:
            sew_target += 1
            revenue += price

    return {
        "revenue_actual": round(revenue, 2),
        "repair_target_deals": repair_target,
        "repair_total_deals": len(repair_all),
        "sew_target_deals": sew_target,
        "sew_total_deals": len(sew_all),
        "sew_new_leads": len(sew_all),
    }
