from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import settings as cfg
from services.excel_oklad import read_oklads
from services.firebird_sales import get_sales_repair, get_sales_cosmetics, get_sales_shoes
from services.advances import advances_for_month
from services.bonuses import bonuses_penalties_for_month
from services.plans_repo import init_db, get_plans, upsert_plan
from services.payroll_calc import calc_employee

app = FastAPI()
templates = Jinja2Templates(directory="templates")

init_db(cfg.SQLITE_DB)

def month_sheet_name(month: int) -> str:
    names = {
        1:"ЯНВАРЬ",2:"ФЕВРАЛЬ",3:"МАРТ",4:"АПРЕЛЬ",5:"МАЙ",6:"ИЮНЬ",
        7:"ИЮЛЬ",8:"АВГУСТ",9:"СЕНТЯБРЬ",10:"ОКТЯБРЬ",11:"НОЯБРЬ",12:"ДЕКАБРЬ"
    }
    if month not in names:
        raise ValueError("month должен быть 1..12")
    return names[month]

@app.get("/", response_class=HTMLResponse)
def index():
    return RedirectResponse(url="/payroll")

@app.get("/payroll", response_class=HTMLResponse)
def payroll_page(request: Request, year: int = 2026, month: int = 2):
    sheet = month_sheet_name(month)

    oklads = read_oklads(str(cfg.EXCEL_FOT), sheet)

    sales_r = get_sales_repair(cfg, year, month)
    sales_c = get_sales_cosmetics(cfg, year, month)
    sales_s = get_sales_shoes(cfg, year, month)

    adv = advances_for_month(str(cfg.ADVANCES_JSON), year, month)
    bon, pen = bonuses_penalties_for_month(str(cfg.BONUSES_JSON), year, month)

    ym = f"{year:04d}-{month:02d}"
    plans = get_plans(cfg.SQLITE_DB, ym)

    rows = []
    for code, oklad in oklads.items():
        pl = plans.get(code, {"repair":0, "cosm":0, "shoes":0})
        r = calc_employee(
            oklad=oklad,
            sales_repair=sales_r.get(code, 0.0),
            sales_cosm=sales_c.get(code, 0.0),
            sales_shoes=sales_s.get(code, 0.0),
            plan_repair=float(pl["repair"]),
            plan_cosm=float(pl["cosm"]),
            plan_shoes=float(pl["shoes"]),
            bonuses=bon.get(code, 0.0),
            penalties=pen.get(code, 0.0),
            advances=adv.get(code, 0.0),
        )
        r["code"] = code
        rows.append(r)

    rows.sort(key=lambda x: x["total"], reverse=True)

    return templates.TemplateResponse("payroll.html", {
        "request": request,
        "year": year, "month": month, "sheet": sheet,
        "rows": rows,
        "ym": ym,
    })

@app.get("/plans", response_class=HTMLResponse)
def plans_page(request: Request, year: int = 2026, month: int = 2):
    ym = f"{year:04d}-{month:02d}"
    sheet = month_sheet_name(month)

    # берём сотрудников из Excel, чтобы показать список строк планов
    oklads = read_oklads(str(cfg.EXCEL_FOT), sheet)
    plans = get_plans(cfg.SQLITE_DB, ym)

    return templates.TemplateResponse("plans.html", {
        "request": request,
        "year": year, "month": month, "ym": ym,
        "employees": sorted(oklads.keys()),
        "plans": plans,
    })

@app.post("/plans/save")
def plans_save(
    year: int = Form(...),
    month: int = Form(...),
    emp_code: str = Form(...),
    plan_repair: float = Form(0),
    plan_cosm: float = Form(0),
    plan_shoes: float = Form(0),
):
    ym = f"{year:04d}-{month:02d}"
    upsert_plan(cfg.SQLITE_DB, ym, emp_code, plan_repair, plan_cosm, plan_shoes)
    return RedirectResponse(url=f"/plans?year={year}&month={month}", status_code=303)
