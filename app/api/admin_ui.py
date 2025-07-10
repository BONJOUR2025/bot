from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(prefix="/admin")


@router.get("/", include_in_schema=False)
async def admin_root() -> FileResponse:
    """Return the bundled admin interface."""
    root_path = Path(__file__).resolve().parent.parent.parent
    return FileResponse(root_path / "UI_full.html")


@router.get("/employees", response_class=HTMLResponse)
async def admin_employees(request: Request):
    return templates.TemplateResponse(
        "admin/employees.html", {"request": request})


@router.get("/payouts", response_class=HTMLResponse)
async def admin_payouts(request: Request):
    return templates.TemplateResponse(
        "admin/payouts.html", {"request": request})


@router.get("/reports", response_class=HTMLResponse)
async def admin_reports(request: Request):
    return templates.TemplateResponse(
        "admin/reports.html", {"request": request})


@router.get("/analytics/sales", response_class=HTMLResponse)
async def admin_sales(request: Request):
    return templates.TemplateResponse(
        "admin/analytics_sales.html", {"request": request})



@router.get("/broadcasts", response_class=HTMLResponse)
async def admin_broadcasts(request: Request):
    return templates.TemplateResponse(
        "admin/broadcasts.html", {"request": request})


@router.get("/vacations", response_class=HTMLResponse)
async def admin_vacations(request: Request):
    return templates.TemplateResponse(
        "admin/vacations.html", {"request": request})


@router.get("/adjustments", response_class=HTMLResponse)
async def admin_adjustments(request: Request):
    return templates.TemplateResponse(
        "admin/adjustments.html", {"request": request})


@router.get("/settings", response_class=HTMLResponse)
async def admin_settings(request: Request):
    return templates.TemplateResponse(
        "admin/settings.html", {"request": request})
