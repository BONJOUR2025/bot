def pct_by_plan(sales: float, plan: float, pct_hi: float, pct_lo: float) -> float:
    if plan and plan > 0:
        return pct_hi if (sales / plan) >= 0.8 else pct_lo
    # если план не задан — берём нижнюю ставку (безопасно)
    return pct_lo

def calc_employee(
    oklad: float,
    sales_repair: float,
    sales_cosm: float,
    sales_shoes: float,
    plan_repair: float,
    plan_cosm: float,
    plan_shoes: float,
    bonuses: float,
    penalties: float,
    advances: float,
) -> dict:
    pct_r = pct_by_plan(sales_repair, plan_repair, 0.02, 0.01)
    pct_c = pct_by_plan(sales_cosm,  plan_cosm,  0.08, 0.05)
    pct_s = pct_by_plan(sales_shoes, plan_shoes, 0.05, 0.03)

    add_r = sales_repair * pct_r
    add_c = sales_cosm  * pct_c
    add_s = sales_shoes * pct_s

    total = oklad + add_r + add_c + add_s + bonuses - advances - penalties

    return {
        "oklad": float(oklad or 0),
        "sales_repair": float(sales_repair or 0), "pct_repair": pct_r, "add_repair": float(add_r or 0), "plan_repair": float(plan_repair or 0),
        "sales_cosm": float(sales_cosm or 0),     "pct_cosm": pct_c,   "add_cosm": float(add_c or 0),   "plan_cosm": float(plan_cosm or 0),
        "sales_shoes": float(sales_shoes or 0),   "pct_shoes": pct_s,  "add_shoes": float(add_s or 0),  "plan_shoes": float(plan_shoes or 0),
        "bonuses": float(bonuses or 0),
        "penalties": float(penalties or 0),
        "advances": float(advances or 0),
        "total": float(total or 0),
    }
