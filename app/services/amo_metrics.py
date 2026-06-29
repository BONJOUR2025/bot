"""Compute manager KPI metrics from amoCRM for a period.

Attribution:
  * Denominator of conversion — deals CREATED in the period (created_at), per
    pipeline, by the manager (responsible_user_id).
  * Numerator of conversion AND revenue — deals that REACHED a target stage
    («Заказ создан» / «Успешно реализовано») DURING the period, by the date of
    the stage transition (read from /api/v4/events, lead_status_changed). A
    status-change event implies the deal was moved onto the stage.
  * sew new leads — deals created in the period in the sew pipeline.

When ``detail=True`` the result also carries ``items`` — the concrete deals
that landed in each calculation group, with a technical reason — for the
drill-down/debug panel on the page.
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

PIPELINE_NAMES = {PIPELINE_REPAIR: "Мастерская (ремонт)", PIPELINE_SEW: "Обувь (пошив)"}
STAGE_NAMES = {
    STAGE_ORDER_CREATED_REPAIR: "Заказ создан",
    STAGE_ORDER_CREATED_SEW: "Заказ создан",
    STAGE_WON: "Успешно реализовано",
}


def _fmt_ts(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


async def _fetch_pipeline_leads(pipeline_id: int, ts_from: int, ts_to: int,
                                amo_user_id: int | None) -> list[dict]:
    """All leads created in the period in a pipeline (conversion denominator).

    Deduplicated by lead id; pagination stops as soon as a page brings no new
    ids (guards against amoCRM returning the same page / not advancing, which
    would otherwise inflate the counts)."""
    by_id: dict[int, dict] = {}
    page = 1
    while page <= 200:
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
        new = 0
        for l in batch:
            lid = l.get("id")
            if lid is not None and lid not in by_id:
                by_id[lid] = l
                new += 1
        if len(batch) < 250 or new == 0:
            break
        page += 1
    return list(by_id.values())


def _event_stage(ev: dict) -> tuple[int | None, int | None]:
    after = ev.get("value_after")
    if isinstance(after, list) and after:
        after = after[0]
    if isinstance(after, dict):
        ls = after.get("lead_status") or after
        return ls.get("id"), ls.get("pipeline_id")
    return None, None


async def _leads_reached_target(ts_from: int, ts_to: int) -> dict[int, dict]:
    """lead_id -> {pipeline, stage, ts} for leads that reached a target stage in
    the period (latest target transition kept)."""
    reached: dict[int, dict] = {}
    seen_events: set = set()
    page = 1
    while page <= 500:
        data = await amo_get("/events", params={
            "filter[type]": "lead_status_changed",
            "filter[created_at][from]": ts_from,
            "filter[created_at][to]": ts_to,
            "limit": 100,
            "page": page,
        })
        batch = data.get("_embedded", {}).get("events", [])
        if not batch:
            break
        new = 0
        for ev in batch:
            eid = ev.get("id")
            if eid in seen_events:        # skip duplicate events across pages
                continue
            seen_events.add(eid)
            new += 1
            sid, pid = _event_stage(ev)
            lead_id = ev.get("entity_id")
            ts = ev.get("created_at", 0)
            if lead_id is None or sid is None:
                continue
            is_target = (pid == PIPELINE_REPAIR and sid in REPAIR_TARGET_STAGES) or \
                        (pid == PIPELINE_SEW and sid in SEW_TARGET_STAGES)
            if not is_target:
                continue
            # Keep ONLY the last target transition per lead → a deal is counted once.
            cur = reached.get(lead_id)
            if cur is None or ts >= cur["ts"]:
                reached[lead_id] = {"pipeline": pid, "stage": sid, "ts": ts}
        if len(batch) < 100 or new == 0:   # no progress → stop (avoids dup inflation)
            break
        page += 1
    return reached


async def _fetch_leads_by_ids(ids: list[int]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    CHUNK = 50
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i:i + CHUNK]
        data = await amo_get("/leads", params={"filter[id][]": chunk, "limit": CHUNK})
        for lead in data.get("_embedded", {}).get("leads", []):
            out[lead.get("id")] = lead
    return out


async def compute_metrics(date_from: datetime, date_to: datetime,
                          amo_user_id: int | None, detail: bool = False) -> dict:
    ts_from, ts_to = int(date_from.timestamp()), int(date_to.timestamp())

    repair_all = await _fetch_pipeline_leads(PIPELINE_REPAIR, ts_from, ts_to, amo_user_id)
    sew_all = await _fetch_pipeline_leads(PIPELINE_SEW, ts_from, ts_to, amo_user_id)

    reached = await _leads_reached_target(ts_from, ts_to)
    info = await _fetch_leads_by_ids(list(reached.keys())) if reached else {}

    items = {"revenue": [], "repair_num": [], "repair_denom": [],
             "sew_num": [], "sew_denom": []} if detail else None

    repair_target = sew_target = 0
    revenue = 0.0
    for lead_id, meta in reached.items():
        lead = info.get(lead_id)
        if not lead:
            continue
        if amo_user_id and lead.get("responsible_user_id") != amo_user_id:
            continue
        price = float(lead.get("price") or 0)
        pid, sid = meta["pipeline"], meta["stage"]
        revenue += price
        if pid == PIPELINE_REPAIR:
            repair_target += 1
        elif pid == PIPELINE_SEW:
            sew_target += 1
        if detail:
            row = {
                "id": lead_id, "name": lead.get("name", ""), "price": price,
                "date": _fmt_ts(meta["ts"]),
                "reason": f"дошёл до «{STAGE_NAMES.get(sid, sid)}» ({PIPELINE_NAMES.get(pid, pid)}) "
                          f"{_fmt_ts(meta['ts'])} — событием смены статуса; идёт в выручку"
                          + (" и в числитель конверсии" if pid in (PIPELINE_REPAIR, PIPELINE_SEW) else ""),
            }
            items["revenue"].append(row)
            (items["repair_num"] if pid == PIPELINE_REPAIR else items["sew_num"]).append(row)

    if detail:
        for grp, leads, pname in (("repair_denom", repair_all, PIPELINE_NAMES[PIPELINE_REPAIR]),
                                   ("sew_denom", sew_all, PIPELINE_NAMES[PIPELINE_SEW])):
            for l in leads:
                items[grp].append({
                    "id": l.get("id"), "name": l.get("name", ""),
                    "price": float(l.get("price") or 0),
                    "date": _fmt_ts(l.get("created_at")),
                    "reason": f"создан {_fmt_ts(l.get('created_at'))} в воронке {pname} — в знаменателе конверсии",
                })

    result = {
        "revenue_actual": round(revenue, 2),
        "repair_target_deals": repair_target,
        "repair_total_deals": len(repair_all),
        "sew_target_deals": sew_target,
        "sew_total_deals": len(sew_all),
        "sew_new_leads": len(sew_all),
    }
    if detail:
        result["items"] = items
    return result
