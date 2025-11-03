from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from telegram import Update
from pathlib import Path

from ..config import TOKEN
from ..core.application import create_application
from .employees import create_employee_router
from .salary import create_salary_router
from .schedule import create_schedule_router
from .payouts import create_payout_router
from .telegram import create_telegram_router
from ..services.employee_service import EmployeeService, EmployeeAPIService
from ..services.salary_service import SalaryService
from ..services.schedule_service import ScheduleService
from ..services.payout_service import PayoutService
from ..services.telegram_service import TelegramService
from ..services.vacation_service import VacationService
from ..services.adjustment_service import AdjustmentService
from ..services.message_service import MessageService
from .vacations import create_vacation_router
from .adjustments import create_adjustment_router
from .birthdays import create_birthday_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Telegram Bot API",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    telegram_app = None
    if TOKEN and TOKEN != "dummy":
        telegram_app = create_application()
    # Mount static files for admin UI and React frontend
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/status", response_class=HTMLResponse)
    async def status_page():
        return "<h1>\u0421\u0435\u0440\u0432\u0435\u0440 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442</h1>"

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return Response(status_code=204)

    @app.get("/ping")
    async def ping():
        return {"status": "ok"}

    if telegram_app is not None:

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
    app.include_router(create_employee_router(employee_api), prefix="/api")

    salary_service = SalaryService(employee_service._repo)
    app.include_router(create_salary_router(salary_service), prefix="/api")

    schedule_service = ScheduleService()
    app.include_router(create_schedule_router(schedule_service), prefix="/api")

    telegram_service = TelegramService(employee_service._repo)
    payout_service = PayoutService(telegram_service=telegram_service)
    app.include_router(create_payout_router(payout_service), prefix="/api")

    vacation_service = VacationService()
    app.include_router(create_vacation_router(vacation_service), prefix="/api")

    adjustment_service = AdjustmentService()
    app.include_router(create_adjustment_router(adjustment_service), prefix="/api")

    from .incentives import create_incentive_router
    from ..services.incentive_service import IncentiveService

    incentive_service = IncentiveService()
    app.include_router(create_incentive_router(incentive_service), prefix="/api")


    from .assets import create_asset_router
    from ..services.asset_service import AssetService

    asset_service = AssetService()
    app.include_router(create_asset_router(asset_service), prefix="/api")

    from .messages import create_message_router
    from ..services.template_service import TemplateService

    message_service = MessageService(employee_repo=employee_service._repo)
    template_service = TemplateService()
    app.include_router(
        create_message_router(message_service, template_service), prefix="/api"
    )

    from .config import create_config_router
    from ..services.config_service import ConfigService

    config_service = ConfigService()
    app.include_router(create_config_router(config_service), prefix="/api")

    from .dictionary import create_dictionary_router
    from ..services.dictionary_service import DictionaryService

    dictionary_service = DictionaryService()
    app.include_router(create_dictionary_router(dictionary_service), prefix="/api")

    app.include_router(create_birthday_router(), prefix="/api")

    app.include_router(create_telegram_router(employee_service._repo), prefix="/api")

    frontend_path = (
        Path(__file__).resolve().parent.parent.parent / "admin_frontend" / "dist"
    )
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

    if frontend_path.exists():

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str, request: Request):
            file_path = frontend_path / full_path
            if file_path.is_file():
                return FileResponse(str(file_path))
            index_path = frontend_path / "index.html"
            if index_path.exists():
                return HTMLResponse(index_path.read_text())
            return Response(status_code=404)

    if telegram_app is not None:

        @app.post("/webhook")
        async def webhook(request: Request):
            data = await request.json()
            update = Update.de_json(data, telegram_app.bot)
            await telegram_app.process_update(update)
            return {"status": "ok"}

    return app
