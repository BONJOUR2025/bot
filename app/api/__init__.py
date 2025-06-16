from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from telegram import Update

from ..core.application import create_application
from .employees import create_employee_router
from ..services.employee_service import EmployeeService, EmployeeAPIService


def create_app() -> FastAPI:
    app = FastAPI()
    telegram_app = create_application()
    # Path to the Jinja templates is fixed so it works regardless of where the
    # application is started from.
    templates = Jinja2Templates(directory="app/templates")
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.on_event("startup")
    async def startup():
        await telegram_app.initialize()
        await telegram_app.start()

    @app.on_event("shutdown")
    async def shutdown():
        await telegram_app.stop()
        await telegram_app.shutdown()

    employee_service = EmployeeService()
    employee_api = EmployeeAPIService(employee_service)
    app.include_router(create_employee_router(employee_api))

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index(request: Request):
        return templates.TemplateResponse("admin/employees.html", {"request": request})

    @app.get("/payouts", response_class=HTMLResponse, include_in_schema=False)
    async def payouts(request: Request):
        return templates.TemplateResponse("admin/payouts.html", {"request": request})

    @app.get("/reports", response_class=HTMLResponse, include_in_schema=False)
    async def reports(request: Request):
        return templates.TemplateResponse("admin/reports.html", {"request": request})

    @app.get("/birthdays", response_class=HTMLResponse, include_in_schema=False)
    async def birthdays(request: Request):
        return templates.TemplateResponse("admin/birthdays.html", {"request": request})

    @app.get("/broadcasts", response_class=HTMLResponse, include_in_schema=False)
    async def broadcasts(request: Request):
        return templates.TemplateResponse("admin/broadcasts.html", {"request": request})

    @app.get("/settings", response_class=HTMLResponse, include_in_schema=False)
    async def settings(request: Request):
        return templates.TemplateResponse("admin/settings.html", {"request": request})

    @app.post("/webhook")
    async def webhook(request: Request):
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        return {"status": "ok"}

    return app
