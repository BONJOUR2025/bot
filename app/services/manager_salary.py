"""Manager salary = оклад + KPI.

``kpi_max`` is the TARGET (100%) of KPI, not a hard ceiling — over-performance is
paid. KPI is three weighted components (per the BONJOUR scheme):

  1) Выполнение плана по выручке      — вес 35%
  2) Конверсия сделок ремонта         — вес 20%   (воронка 5257981)
  3) Конверсия сделок пошива          — вес 20%   (воронка 5260939)

For every component:  ratio = факт / план.
  * if ratio < 0.79          → component = 0   (порог 79%)
  * else                     → component = ratio * max_component   (no upper cap)
Пошив additionally zeroes out if new leads in the period < 50.

The amoCRM aggregation lives elsewhere; this module is pure math so it can be
unit-tested and reused regardless of where the metrics come from.
"""
from __future__ import annotations

THRESHOLD = 0.79   # ratio below this → component pays 0

# Default component weights (share of kpi_max). Configurable per call.
W_REVENUE = 0.35
W_REPAIR = 0.20
W_SEW = 0.20

# amoCRM identifiers (defaults; overridable in config/UI)
PIPELINE_REPAIR = 5257981   # NEW Мастерская Бонжур
PIPELINE_SEW = 5260939      # NEW Обувь на заказ
STAGE_ORDER_CREATED_REPAIR = 47703040
STAGE_ORDER_CREATED_SEW = 46942927
STAGE_WON = 142             # «Успешно реализовано» (built-in won status)
SEW_MIN_LEADS = 50


def _component(actual: float, plan: float, max_amount: float, *, gate_ok: bool = True) -> dict:
    """Return {ratio, amount, zeroed} for one KPI component."""
    if not gate_ok or plan <= 0:
        return {"ratio": 0.0, "amount": 0.0, "zeroed": True}
    ratio = actual / plan
    if ratio < THRESHOLD:
        return {"ratio": round(ratio, 4), "amount": 0.0, "zeroed": True}
    amount = round(ratio * max_amount, 2)   # no upper cap — over-performance pays
    return {"ratio": round(ratio, 4), "amount": amount, "zeroed": False}


def calc_manager_salary(
    *,
    oklad: float,
    kpi_max: float,
    # weights (share of kpi_max)
    w_revenue: float = W_REVENUE,
    w_repair: float = W_REPAIR,
    w_sew: float = W_SEW,
    # 1) revenue
    revenue_plan: float,
    revenue_actual: float,
    # 2) repair conversion
    repair_plan_conv: float,
    repair_target_deals: int,
    repair_total_deals: int,
    # 3) sew conversion
    sew_plan_conv: float,
    sew_target_deals: int,
    sew_total_deals: int,
    sew_new_leads: int,
    sew_min_leads: int = SEW_MIN_LEADS,
    advances: float = 0.0,
) -> dict:
    oklad = float(oklad or 0)
    kpi_max = float(kpi_max or 0)
    advances = float(advances or 0)

    max_rev = round(kpi_max * w_revenue, 2)
    max_rep = round(kpi_max * w_repair, 2)
    max_sew = round(kpi_max * w_sew, 2)

    c_rev = _component(float(revenue_actual or 0), float(revenue_plan or 0), max_rev)

    rep_conv = (repair_target_deals / repair_total_deals) if repair_total_deals else 0.0
    c_rep = _component(rep_conv, float(repair_plan_conv or 0), max_rep)
    c_rep["conv"] = round(rep_conv, 4)

    sew_conv = (sew_target_deals / sew_total_deals) if sew_total_deals else 0.0
    c_sew = _component(
        sew_conv, float(sew_plan_conv or 0), max_sew,
        gate_ok=int(sew_new_leads or 0) >= sew_min_leads,
    )
    c_sew["conv"] = round(sew_conv, 4)
    c_sew["leads_gate_failed"] = int(sew_new_leads or 0) < sew_min_leads

    kpi = round(c_rev["amount"] + c_rep["amount"] + c_sew["amount"], 2)
    gross = round(oklad + kpi, 2)
    to_pay = round(gross - advances, 2)
    return {
        "oklad": oklad,
        "kpi_max": kpi_max,
        "weights": {"revenue": w_revenue, "repair": w_repair, "sew": w_sew},
        "revenue": {**c_rev, "max": max_rev, "plan": float(revenue_plan or 0), "actual": float(revenue_actual or 0)},
        "repair": {**c_rep, "max": max_rep, "plan_conv": float(repair_plan_conv or 0),
                   "target": int(repair_target_deals or 0), "total": int(repair_total_deals or 0)},
        "sew": {**c_sew, "max": max_sew, "plan_conv": float(sew_plan_conv or 0),
                "target": int(sew_target_deals or 0), "total": int(sew_total_deals or 0),
                "new_leads": int(sew_new_leads or 0), "min_leads": sew_min_leads},
        "kpi": kpi,
        "gross": gross,
        "advances": advances,
        "to_pay": to_pay,
    }
