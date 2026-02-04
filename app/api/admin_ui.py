from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(prefix="/admin")


@router.get("/", include_in_schema=False)
async def admin_root() -> FileResponse:
    """Return the bundled admin interface."""
    root_path = Path(__file__).resolve().parent.parent.parent
    return FileResponse(root_path / "UI_full.html")


def _render(template_name: str, request: Request) -> HTMLResponse:
    return templates.TemplateResponse(template_name, {"request": request})


@router.get("/employees", response_class=HTMLResponse)
async def admin_employees(request: Request) -> HTMLResponse:
    return _render("admin/employees.html", request)


@router.get("/payouts", response_class=HTMLResponse)
async def admin_payouts(request: Request) -> HTMLResponse:
    return _render("admin/payouts.html", request)


@router.get("/reports", response_class=HTMLResponse)
async def admin_reports(request: Request) -> HTMLResponse:
    return _render("admin/reports.html", request)


@router.get("/broadcasts", response_class=HTMLResponse)
async def admin_broadcasts(request: Request) -> HTMLResponse:
    return _render("admin/broadcasts.html", request)


@router.get("/vacations", response_class=HTMLResponse)
async def admin_vacations(request: Request) -> HTMLResponse:
    return _render("admin/vacations.html", request)


@router.get("/adjustments", response_class=HTMLResponse)
async def admin_adjustments(request: Request) -> HTMLResponse:
    return _render("admin/adjustments.html", request)


@router.get("/settings", response_class=HTMLResponse)
async def admin_settings(request: Request) -> HTMLResponse:
    return _render("admin/settings.html", request)
