"""Compute manager KPI metrics from amoCRM for a period.

Produces the six numbers the salary engine needs (revenue, repair/sew target &
total deal counts, sew new-lead count) following the BONJOUR spec:

  * deals are counted in the расчётный период by created_at
  * target deals (числитель конверсии) must be MOVED onto the target stage,
    not created in it — approximated by updated_at > created_at, since /leads
    does not expose stage history
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


def _is_moved(lead: dict) -> bool:
    # Heuristic: a lead that was moved onto a stage has updated_at > created_at.
    return int(lead.get("updated_at", 0)) > int(lead.get("created_at", 0))


async def compute_metrics(date_from: datetime, date_to: datetime,
                          amo_user_id: int | None) -> dict:
    ts_from, ts_to = int(date_from.timestamp()), int(date_to.timestamp())

    repair = await _fetch_pipeline_leads(PIPELINE_REPAIR, ts_from, ts_to, amo_user_id)
    sew = await _fetch_pipeline_leads(PIPELINE_SEW, ts_from, ts_to, amo_user_id)

    def _targets(leads, stages):
        return [l for l in leads if l.get("status_id") in stages and _is_moved(l)]

    repair_targets = _targets(repair, REPAIR_TARGET_STAGES)
    sew_targets = _targets(sew, SEW_TARGET_STAGES)

    # Revenue: sum price of deals on the target stages (created in period),
    # across both pipelines — no "moved" requirement per spec.
    revenue = sum(float(l.get("price") or 0)
                  for l in repair if l.get("status_id") in REPAIR_TARGET_STAGES)
    revenue += sum(float(l.get("price") or 0)
                   for l in sew if l.get("status_id") in SEW_TARGET_STAGES)

    return {
        "revenue_actual": round(revenue, 2),
        "repair_target_deals": len(repair_targets),
        "repair_total_deals": len(repair),
        "sew_target_deals": len(sew_targets),
        "sew_total_deals": len(sew),
        "sew_new_leads": len(sew),  # новые лиды пошива за период
    }
