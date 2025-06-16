from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from telegram import Update

from ..core.application import create_application
from .employees import create_employee_router
from .salary import create_salary_router
from ..services.employee_service import EmployeeService, EmployeeAPIService
from ..services.salary_service import SalaryService


def create_app() -> FastAPI:
    app = FastAPI()
    telegram_app = create_application()
    # Mount static files for admin UI
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

    salary_service = SalaryService(employee_service._repo)
    app.include_router(create_salary_router(salary_service))

    # Admin UI routes
    from .admin_ui import router as admin_router
    app.include_router(admin_router, include_in_schema=False)

    @app.post("/webhook")
    async def webhook(request: Request):
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        return {"status": "ok"}

    return app
