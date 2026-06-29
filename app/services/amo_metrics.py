"""Compute manager KPI metrics from amoCRM for a period.

Attribution:
  * Denominator of conversion — deals CREATED in the period (created_at), per
    pipeline, by the manager (responsible_user_id).
  * Numerator of conversion AND revenue — deals that REACHED the «Заказ создан»
    stage DURING the period, by the date of THAT transition (read from
    /api/v4/events, lead_status_changed). Reaching «Заказ создан» = the order was
    created = success; later stages («Успешно реализовано» etc.) don't matter.
    The first move onto «Заказ создан» is the fixed date. A deal is counted only
    if it is still in the same KPI pipeline at calculation time.
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

# Conversion success is triggered ONLY by reaching «Заказ создан».
REPAIR_TARGET_STAGES = {STAGE_ORDER_CREATED_REPAIR}
SEW_TARGET_STAGES = {STAGE_ORDER_CREATED_SEW}

# The two KPI pipelines; a move across this boundary is a control signal.
KPI_PIPELINES = {PIPELINE_REPAIR, PIPELINE_SEW}

# «Неразобранное» — входящая воронка. Перемещение ИЗ неё в рабочую воронку —
# это нормальный разбор лида, а не подозрительная реклассификация.
PIPELINE_UNSORTED = 1611361

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


def _event_value(node) -> tuple[int | None, int | None]:
    """Parse one side (value_before / value_after) of a lead_status_changed
    event into (status_id, pipeline_id)."""
    if isinstance(node, list) and node:
        node = node[0]
    if isinstance(node, dict):
        ls = node.get("lead_status") or node
        return ls.get("id"), ls.get("pipeline_id")
    return None, None


async def _fetch_pipeline_names() -> dict[int, str]:
    """id -> name for every pipeline (so cross-pipeline moves читаются по-русски)."""
    try:
        data = await amo_get("/leads/pipelines")
        return {p.get("id"): p.get("name", str(p.get("id")))
                for p in data.get("_embedded", {}).get("pipelines", [])}
    except Exception:
        return {}


async def _scan_status_events(ts_from: int, ts_to: int) -> tuple[dict[int, dict], list[dict]]:
    """Single sweep over lead_status_changed events in the period, returning:
      * reached: lead_id -> {pipeline, stage, ts} for leads that reached a KPI
        «Заказ создан» stage (FIRST such transition kept);
      * moves:   list of {lead_id, from, to, ts} for events where the pipeline
        changed (value_before.pipeline_id != value_after.pipeline_id)."""
    reached: dict[int, dict] = {}
    moves: list[dict] = []
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
            lead_id = ev.get("entity_id")
            ts = ev.get("created_at", 0)
            if lead_id is None:
                continue
            _, before_pid = _event_value(ev.get("value_before"))
            after_sid, after_pid = _event_value(ev.get("value_after"))

            # 1) reached a KPI target stage
            if after_sid is not None and (
                (after_pid == PIPELINE_REPAIR and after_sid in REPAIR_TARGET_STAGES)
                or (after_pid == PIPELINE_SEW and after_sid in SEW_TARGET_STAGES)
            ):
                cur = reached.get(lead_id)
                if cur is None or ts < cur["ts"]:   # keep FIRST «Заказ создан»
                    reached[lead_id] = {"pipeline": after_pid, "stage": after_sid, "ts": ts}

            # 2) cross-pipeline move
            if before_pid is not None and after_pid is not None and before_pid != after_pid:
                moves.append({"lead_id": lead_id, "from": before_pid, "to": after_pid, "ts": ts})
        if len(batch) < 100 or new == 0:   # no progress → stop (avoids dup inflation)
            break
        page += 1
    return reached, moves


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

    reached, moves = await _scan_status_events(ts_from, ts_to)

    # Suspicious = cross-pipeline moves touching a KPI pipeline (in/out/between),
    # excluding the normal intake move out of «Неразобранное».
    kpi_moves = [m for m in moves
                 if (m["from"] in KPI_PIPELINES or m["to"] in KPI_PIPELINES)
                 and m["from"] != PIPELINE_UNSORTED]

    need_ids = set(reached.keys())
    if detail:
        need_ids |= {m["lead_id"] for m in kpi_moves}
    info = await _fetch_leads_by_ids(list(need_ids)) if need_ids else {}

    items = {"revenue": [], "repair_num": [], "repair_denom": [],
             "sew_num": [], "sew_denom": [], "excluded": [], "suspicious": []} if detail else None

    repair_target = sew_target = 0
    revenue = 0.0
    for lead_id, meta in reached.items():
        lead = info.get(lead_id)
        if not lead:
            continue
        pid, sid = meta["pipeline"], meta["stage"]
        price = float(lead.get("price") or 0)
        cur_pipe = lead.get("pipeline_id")
        resp = lead.get("responsible_user_id")

        # Reasons a deal that reached a target stage is NOT counted:
        drop = None
        if amo_user_id and resp != amo_user_id:
            drop = f"ответственный {resp} ≠ менеджер {amo_user_id}"
        elif cur_pipe != pid:
            drop = (f"сейчас в воронке {cur_pipe} (ушла из «{PIPELINE_NAMES.get(pid, pid)}») "
                    f"— реклассификация/дубль, не зачитывается")
        if drop:
            if detail:
                items["excluded"].append({
                    "id": lead_id, "name": lead.get("name", ""), "price": price,
                    "date": _fmt_ts(meta["ts"]),
                    "reason": f"достигла «{STAGE_NAMES.get(sid, sid)}» {_fmt_ts(meta['ts'])}, но НЕ зачтена: {drop}",
                })
            continue

        revenue += price
        if pid == PIPELINE_REPAIR:
            repair_target += 1
        elif pid == PIPELINE_SEW:
            sew_target += 1
        if detail:
            row = {
                "id": lead_id, "name": lead.get("name", ""), "price": price,
                "date": _fmt_ts(meta["ts"]),
                "reason": f"дошла до «{STAGE_NAMES.get(sid, sid)}» ({PIPELINE_NAMES.get(pid, pid)}) "
                          f"{_fmt_ts(meta['ts'])}; в выручке и в числителе конверсии",
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

        # Suspicious cross-pipeline movements (control): a deal that arrived from
        # another pipeline into a KPI pipeline, left a KPI pipeline, or hopped
        # between the two KPI pipelines — attributed to this manager.
        pipe_names = await _fetch_pipeline_names()

        def _pname(pid):
            return pipe_names.get(pid) or PIPELINE_NAMES.get(pid) or f"воронка {pid}"

        seen = set()
        for m in sorted(kpi_moves, key=lambda x: x["ts"]):
            lead = info.get(m["lead_id"])
            if not lead:
                continue
            if amo_user_id and lead.get("responsible_user_id") != amo_user_id:
                continue
            frm, to = m["from"], m["to"]
            key = (m["lead_id"], frm, to, m["ts"])
            if key in seen:
                continue
            seen.add(key)
            if frm in KPI_PIPELINES and to in KPI_PIPELINES:
                direction, tag = "between", "переход между KPI-воронками"
            elif to in KPI_PIPELINES:
                direction, tag = "in", "пришла из другой воронки"
            else:
                direction, tag = "out", "перенесена в другую воронку"
            items["suspicious"].append({
                "id": m["lead_id"], "name": lead.get("name", ""),
                "price": float(lead.get("price") or 0), "date": _fmt_ts(m["ts"]),
                "direction": direction,
                "reason": f"{tag}: «{_pname(frm)}» → «{_pname(to)}» ({_fmt_ts(m['ts'])})",
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
