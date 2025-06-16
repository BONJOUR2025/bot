from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def admin_root(request: Request):
    return templates.TemplateResponse("admin/layout.html", {"request": request})

@router.get("/employees", response_class=HTMLResponse)
async def admin_employees(request: Request):
    return templates.TemplateResponse("admin/employees.html", {"request": request})

@router.get("/payouts", response_class=HTMLResponse)
async def admin_payouts(request: Request):
    return templates.TemplateResponse("admin/payouts.html", {"request": request})

@router.get("/reports", response_class=HTMLResponse)
async def admin_reports(request: Request):
    return templates.TemplateResponse("admin/reports.html", {"request": request})

@router.get("/birthdays", response_class=HTMLResponse)
async def admin_birthdays(request: Request):
    return templates.TemplateResponse("admin/birthdays.html", {"request": request})

@router.get("/broadcasts", response_class=HTMLResponse)
async def admin_broadcasts(request: Request):
    return templates.TemplateResponse("admin/broadcasts.html", {"request": request})

@router.get("/settings", response_class=HTMLResponse)
async def admin_settings(request: Request):
    return templates.TemplateResponse("admin/settings.html", {"request": request})
