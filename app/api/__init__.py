from fastapi import FastAPI, Depends, Request
from fastapi.responses import FileResponse
from pathlib import Path
from telegram import Update

from ..core.application import create_application
from .auth import check_token
from .employees import create_employee_router
from ..services.employee_service import EmployeeService, EmployeeAPIService


def create_app() -> FastAPI:
    app = FastAPI()
    telegram_app = create_application()

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
    app.include_router(
        create_employee_router(employee_api),
        dependencies=[Depends(check_token)],
    )

    @app.get("/", include_in_schema=False)
    async def index():
        path = Path(__file__).resolve().parents[2] / "UI_full.html"
        return FileResponse(path)

    @app.post("/webhook")
    async def webhook(request: Request):
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        return {"status": "ok"}

    return app
