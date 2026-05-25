from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, Request, status
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from telegram import Update

from app.services.access_control_service import (
    TOKEN_TTL_SECONDS,
    get_access_control_service,
)
from app.schemas.auth import LoginRequest

from ..config import TOKEN
from ..core.application import create_application
from ..services.adjustment_service import AdjustmentService
from ..services.employee_service import EmployeeAPIService, EmployeeService
from ..services.message_service import MessageService
from ..services.payout_service import PayoutService
from ..services.salary_service import SalaryService
from ..services.schedule_service import ScheduleService
from ..services.telegram_service import TelegramService
from ..services.vacation_service import VacationService
from .adjustments import create_adjustment_router
from .assets import create_asset_router
from .auth import create_auth_router
from .birthdays import create_birthday_router
from .config import create_config_router
from .dependencies import get_current_user
from .dictionary import create_dictionary_router
from .employees import create_employee_router
from .incentives import create_incentive_router
from .messages import create_message_router
from .payouts import create_payout_router
from .salary import create_salary_router
from .schedule import create_schedule_router
from .telegram import create_telegram_router
from .vacations import create_vacation_router
from .payroll import create_payroll_router
from .tasks import create_task_router
from .passwords import create_password_router
from .push import create_push_router

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

    # Статика для админки/React
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

    access_service = get_access_control_service()
    app.include_router(create_auth_router(access_service), prefix="/api")

    @app.get("/", include_in_schema=False)
    async def root_redirect(
        request: Request, access_token: str | None = Cookie(default=None)
    ):
        if access_token:
            try:
                access_service.verify_token(access_token)
                return RedirectResponse(url="/admin", status_code=302)
            except ValueError:
                pass
        return RedirectResponse(url="/admin/login", status_code=302)

    @app.post("/session/login", include_in_schema=False)
    async def session_login(payload: LoginRequest) -> JSONResponse:
        resolved = access_service.authenticate(payload.login, payload.password)
        if not resolved:
            return JSONResponse(
                {"detail": "invalid_credentials"},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        token = access_service.issue_token(resolved.id)
        response = JSONResponse({"status": "ok", "token": token})
        response.set_cookie(
            "access_token",
            token,
            max_age=TOKEN_TTL_SECONDS,
            httponly=True,
            secure=False,
            samesite="lax",
        )
        return response

    @app.post("/session/logout", include_in_schema=False)
    async def session_logout() -> JSONResponse:
        response = JSONResponse({"status": "ok"})
        response.delete_cookie("access_token")
        return response

    protected = [Depends(get_current_user)]

    employee_service = EmployeeService()
    employee_api = EmployeeAPIService(employee_service)
    app.include_router(
        create_employee_router(employee_api, access_service),
        prefix="/api",
        dependencies=protected,
    )

    salary_service = SalaryService(employee_service._repo)
    app.include_router(
        create_salary_router(salary_service, access_service),
        prefix="/api",
        dependencies=protected,
    )

    schedule_service = ScheduleService()
    app.include_router(
        create_schedule_router(schedule_service), prefix="/api", dependencies=protected
    )

    from ..services.push_service import get_push_service
    push_service = get_push_service()
    app.include_router(
        create_push_router(push_service),
        prefix="/api",
        dependencies=protected,
    )

    telegram_service = TelegramService(employee_service._repo)
    payout_service = PayoutService(telegram_service=telegram_service, push_service=push_service)
    app.include_router(
        create_payout_router(payout_service, access_service),
        prefix="/api",
        dependencies=protected,
    )

    from ..services import cash_move_auto_linker

    @app.on_event("startup")
    async def _start_auto_linker():
        cash_move_auto_linker.start(payout_service)

    @app.on_event("shutdown")
    async def _stop_auto_linker():
        cash_move_auto_linker.stop()

    vacation_service = VacationService()
    app.include_router(
        create_vacation_router(vacation_service, access_service),
        prefix="/api",
        dependencies=protected,
    )

    adjustment_service = AdjustmentService()
    app.include_router(
        create_adjustment_router(adjustment_service), prefix="/api", dependencies=protected
    )

    from ..services.incentive_service import IncentiveService

    incentive_service = IncentiveService()
    app.include_router(
        create_incentive_router(incentive_service, access_service),
        prefix="/api",
        dependencies=protected,
    )

    from ..services.asset_service import AssetService

    asset_service = AssetService()
    app.include_router(
        create_asset_router(asset_service, access_service),
        prefix="/api",
        dependencies=protected,
    )

    from ..services.template_service import TemplateService

    message_service = MessageService(employee_repo=employee_service._repo)
    template_service = TemplateService()
    app.include_router(
        create_message_router(message_service, template_service),
        prefix="/api",
        dependencies=protected,
    )

    from ..services.config_service import ConfigService

    config_service = ConfigService()
    app.include_router(
        create_config_router(config_service), prefix="/api", dependencies=protected
    )

    from ..services.dictionary_service import DictionaryService

    dictionary_service = DictionaryService()
    app.include_router(
        create_dictionary_router(dictionary_service), prefix="/api", dependencies=protected
    )

    app.include_router(create_birthday_router(), prefix="/api", dependencies=protected)

    # Payroll calculation router
    from ..services.payroll_service import get_payroll_service
    from ..data.sales_plans_repository import get_sales_plans_repository

    payroll_service = get_payroll_service()
    plans_repo = get_sales_plans_repository()
    app.include_router(
        create_payroll_router(payroll_service, plans_repo, access_service),
        prefix="/api",
        dependencies=protected,
    )

    app.include_router(
        create_telegram_router(employee_service._repo),
        prefix="/api",
        dependencies=protected,
    )

    # Task manager
    from ..services.task_service import TaskService

    task_service = TaskService()
    app.include_router(
        create_task_router(task_service),
        prefix="/api",
        dependencies=protected,
    )

    # Password vault
    from ..services.password_service import PasswordService

    password_service = PasswordService()
    app.include_router(
        create_password_router(password_service),
        prefix="/api",
        dependencies=protected,
    )

    # Masters / Agbis services dashboard
    from .masters import create_masters_router

    app.include_router(
        create_masters_router(),
        prefix="/api",
        dependencies=protected,
    )

    # Sales analytics
    from .sales import create_sales_router

    app.include_router(
        create_sales_router(),
        prefix="/api",
        dependencies=protected,
    )

    # Salons management
    from .salons import create_salons_router
    from ..data.salon_repository import get_salon_repository

    app.include_router(
        create_salons_router(get_salon_repository()),
        prefix="/api",
        dependencies=protected,
    )

    # Location codes and monthly plans (for payroll auto-plan calculation)
    from .location_plans import create_location_plans_router
    from ..data.location_repository import get_location_repository

    app.include_router(
        create_location_plans_router(get_location_repository()),
        prefix="/api",
        dependencies=protected,
    )

    # Cash movements
    from .cash_moves import create_cash_moves_router
    from ..data.cash_category_repository import get_cash_category_repository
    from ..data.cash_config_repository import get_cash_config_repository

    app.include_router(
        create_cash_moves_router(get_cash_category_repository(), get_cash_config_repository()),
        prefix="/api",
        dependencies=protected,
    )

    # SMS Агбис
    from .smses import create_smses_router

    app.include_router(
        create_smses_router(),
        prefix="/api",
        dependencies=protected,
    )

    # Recruitment CRM
    from .recruitment import router as recruitment_router
    from app.models.recruitment import Vacancy, Candidate, RecruitmentSource, VacancyLink  # noqa: F401
    from app.db.session import init_db as _init_db
    _init_db()
    app.include_router(recruitment_router, prefix="/api", dependencies=protected)

    from app.services import recruitment_sync

    @app.on_event("startup")
    async def _start_recruitment_sync():
        recruitment_sync.start()

    @app.on_event("shutdown")
    async def _stop_recruitment_sync():
        recruitment_sync.stop()

    # Payment calendar
    from .payment_calendar import create_payment_calendar_router
    from app.models.payment_calendar import PaymentSchedule, PaymentRecord  # noqa: F401
    from app.db.session import init_db as _init_db2
    _init_db2()
    app.include_router(
        create_payment_calendar_router(),
        prefix="/api",
        dependencies=protected,
    )

    # System tools (status, backup, archive)
    from .system import create_system_router

    app.include_router(
        create_system_router(),
        prefix="/api",
        dependencies=protected,
    )

    # SPA фронтенд (Vite/React)
    # NOTE: We use explicit routes instead of app.mount() so that SPA routes
    # like /admin/login are served correctly (mount intercepts and returns 404
    # for paths that don't correspond to real files).
    frontend_path = (
        Path(__file__).resolve().parent.parent.parent / "admin_frontend" / "dist"
    )

    @app.get("/admin", include_in_schema=False)
    async def admin_root(request: Request):
        index_path = frontend_path / "index.html"
        if index_path.exists():
            return HTMLResponse(index_path.read_text(encoding="utf-8"))
        return Response(status_code=404)

    @app.get("/admin/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str, request: Request):
        file_path = frontend_path / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        # Don't fall back to SPA for static asset requests (e.g. sw.js, *.png)
        if "." in Path(full_path).name:
            return Response(status_code=404)
        index_path = frontend_path / "index.html"
        if index_path.exists():
            return HTMLResponse(index_path.read_text(encoding="utf-8"))
        return Response(status_code=404)

    @app.get("/employee", include_in_schema=False)
    async def employee_root(request: Request):
        index_path = frontend_path / "index.html"
        if index_path.exists():
            return HTMLResponse(index_path.read_text(encoding="utf-8"))
        return Response(status_code=404)

    @app.get("/employee/{full_path:path}", include_in_schema=False)
    async def employee_spa_fallback(full_path: str, request: Request):
        file_path = frontend_path / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        # Don't fall back to SPA for static asset requests
        if "." in Path(full_path).name:
            return Response(status_code=404)
        index_path = frontend_path / "index.html"
        if index_path.exists():
            return HTMLResponse(index_path.read_text(encoding="utf-8"))
        return Response(status_code=404)

    if telegram_app is not None:

        @app.post("/webhook")
        async def webhook(request: Request):
            data = await request.json()
            update = Update.de_json(data, telegram_app.bot)
            await telegram_app.process_update(update)
            return {"status": "ok"}

    return app
