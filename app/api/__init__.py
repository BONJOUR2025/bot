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
from ..services.employee_message_service import EmployeeMessageService
from ..services.leave_request_service import LeaveRequestService
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
from .employee_messages import create_employee_message_router
from .leave_requests import create_leave_request_router
from .incentives import create_incentive_router
from .messages import create_message_router
from .payouts import create_payout_router
from .manager_salary import create_manager_salary_router
from .courier_salary import create_courier_salary_router
from .amo import create_amo_router
from .salary import create_salary_router
from .schedule import create_schedule_router
from .telegram import create_telegram_router
from .vacations import create_vacation_router
from .payroll import create_payroll_router
from .tasks import create_task_router
from .passwords import create_password_router
from .push import create_push_router
from ..utils.logger import log_connection, log_user_action

def create_app() -> FastAPI:
    app = FastAPI(
        title="Telegram Bot API",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    # Nothing else was compressing responses — the ~1.7 MB JS bundle was
    # going out over the wire uncompressed on every first load.
    from starlette.middleware.gzip import GZipMiddleware
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    telegram_app = None
    if TOKEN and TOKEN != "dummy":
        # with_jobs=False: scheduled jobs (morning briefing, reminders, etc.) must run
        # only in the bot process (app/main.py) — registering them here too would
        # duplicate every scheduled message (e.g. the morning briefing sent twice).
        telegram_app = create_application(with_jobs=False)

    # Статика для админки/React
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.middleware("http")
    async def log_api_activity(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/api") or path.startswith("/session"):
            user = getattr(request.state, "user", None)
            action = f"{request.method} {path} -> {response.status_code}"
            if user:
                label = user.login or user.display_name or user.id
                log_user_action(user.id, label, action)
            else:
                log_user_action("anonymous", None, action)
        return response

    @app.get("/status", response_class=HTMLResponse)
    async def status_page():
        return "<h1>\u0421\u0435\u0440\u0432\u0435\u0440 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442</h1>"

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return Response(status_code=204)

    @app.get("/ping")
    async def ping():
        return {"status": "ok"}

    @app.on_event("startup")
    async def _start_heartbeat():
        import asyncio
        from ..utils.logger import write_heartbeat

        async def _loop():
            while True:
                write_heartbeat("api_server")
                await asyncio.sleep(60)

        asyncio.create_task(_loop())

    @app.on_event("startup")
    async def _widen_thread_pool():
        # Every asyncio.to_thread call in this process (all Firebird
        # queries included) shares one event-loop-wide executor, sized by
        # default to min(32, cpu_count + 4) — on a small VM that can be as
        # few as 6-8 workers, comfortably less than the 12 concurrent
        # requests a single dashboard page load fires. firebird_service's
        # TTLCache makes non-owner callers block their worker thread
        # waiting on whichever call is already computing the same key,
        # rather than yielding it back to the pool — so a burst of
        # same-key dashboard/search requests can tie up several workers
        # just waiting. Widen the pool so that headroom doesn't come out
        # of every other asyncio.to_thread caller in the app.
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=40, thread_name_prefix="api-worker"))

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
        return RedirectResponse(url="/login", status_code=302)

    @app.post("/session/login", include_in_schema=False)
    async def session_login(payload: LoginRequest) -> JSONResponse:
        resolved = access_service.authenticate(payload.login, payload.password)
        if not resolved:
            log_connection(f"Admin: failed login attempt for login={payload.login!r}")
            return JSONResponse(
                {"detail": "invalid_credentials"},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        log_connection(f"Admin: {resolved.login or resolved.id} logged in")
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
    async def session_logout(access_token: str | None = Cookie(default=None)) -> JSONResponse:
        if access_token:
            try:
                resolved = access_service.verify_token(access_token)
                log_connection(f"Admin: {resolved.login or resolved.id} logged out")
            except ValueError:
                pass
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
    app.include_router(
        create_manager_salary_router(payout_service, access_service),
        prefix="/api",
        dependencies=protected,
    )
    app.include_router(
        create_courier_salary_router(payout_service, access_service),
        prefix="/api",
        dependencies=protected,
    )
    app.include_router(create_amo_router(), prefix="/api")

    from ..services import cash_move_auto_linker

    @app.on_event("startup")
    async def _start_auto_linker():
        cash_move_auto_linker.start(payout_service)

    @app.on_event("shutdown")
    async def _stop_auto_linker():
        cash_move_auto_linker.stop()

    from ..services import starline_poller

    @app.on_event("startup")
    async def _start_starline_poller():
        starline_poller.start()

    @app.on_event("shutdown")
    async def _stop_starline_poller():
        starline_poller.stop()

    vacation_service = VacationService()
    app.include_router(
        create_vacation_router(vacation_service, access_service),
        prefix="/api",
        dependencies=protected,
    )

    leave_request_service = LeaveRequestService(
        telegram_service=telegram_service, push_service=push_service
    )
    app.include_router(
        create_leave_request_router(leave_request_service, access_service),
        prefix="/api",
        dependencies=protected,
    )

    employee_message_service = EmployeeMessageService(
        telegram_service=telegram_service, push_service=push_service
    )
    app.include_router(
        create_employee_message_router(employee_message_service, access_service),
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

    asset_service = AssetService(telegram=telegram_service)
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
    from ..services.task_service import get_task_service

    task_service = get_task_service()
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

    # Agbis users directory
    from .agbis_users import create_agbis_users_router

    app.include_router(
        create_agbis_users_router(),
        prefix="/api",
        dependencies=protected,
    )

    # Agbis local settings (per-computer options comparison)
    from .agbis_settings import create_agbis_settings_router

    app.include_router(
        create_agbis_settings_router(),
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

    # Client CRM (Agbis contragents)
    from .clients import create_clients_router

    app.include_router(
        create_clients_router(),
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

    # Shift check-ins (opening shift photo records)
    from .shift_checkins import create_shift_checkins_router
    from ..data.shift_checkin_repository import get_shift_checkin_repository

    app.include_router(
        create_shift_checkins_router(get_shift_checkin_repository()),
        prefix="/api",
        dependencies=protected,
    )

    # Visitor counter (ESP8266 etc.) — ingest endpoint is protected by a static
    # API key (devices can't hold a user session), admin endpoints by permission.
    from .visitor_counters import (
        create_visitor_counter_device_router,
        create_visitor_counter_router,
    )
    from ..services.visitor_counter_service import get_visitor_counter_service

    visitor_counter_service = get_visitor_counter_service()
    app.include_router(
        create_visitor_counter_device_router(visitor_counter_service),
        prefix="/api",
    )
    app.include_router(
        create_visitor_counter_router(visitor_counter_service),
        prefix="/api",
        dependencies=protected,
    )

    # 3D foot scanner (.scm file parsing -> metadata + measurements + views)
    from .scanner import create_scanner_router

    app.include_router(
        create_scanner_router(),
        prefix="/api",
        dependencies=protected,
    )

    # Shoe-last (колодка) library + foot-scan matching
    from .lasts import create_lasts_router

    app.include_router(
        create_lasts_router(),
        prefix="/api",
        dependencies=protected,
    )

    # Shoe-last article/model number registry (dropdown source for the "add
    # a last" form + a separate editable list of known numbers)
    from .last_articles import create_last_articles_router

    app.include_router(
        create_last_articles_router(),
        prefix="/api",
        dependencies=protected,
    )

    # Bot users (Telegram users who have started the bot, linkable to employees)
    from .bot_users import create_bot_users_router
    from ..data.bot_user_repository import get_bot_user_repository

    app.include_router(
        create_bot_users_router(get_bot_user_repository()),
        prefix="/api",
        dependencies=protected,
    )

    # VK users (same idea as bot-users above, for a future VK bot — the
    # repository/API are ready, only the VK bot's own touch() call is missing)
    from .vk_bot_users import create_vk_bot_users_router
    from ..data.vk_bot_user_repository import get_vk_bot_user_repository

    app.include_router(
        create_vk_bot_users_router(get_vk_bot_user_repository()),
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
    from app.models.asset import Asset as AssetModel  # noqa: F401  — registers table with Base
    from app.db.session import init_db as _init_db
    _init_db()
    app.include_router(recruitment_router, prefix="/api", dependencies=protected)

    # Avito message webhook — deliberately NOT behind `protected`: Avito can't
    # present a session token, so the secret in the URL path authenticates it
    # (see app/api/avito_webhook.py).
    from .avito_webhook import router as avito_webhook_router
    app.include_router(avito_webhook_router, prefix="/api")

    from .hh_webhook import router as hh_webhook_router
    app.include_router(hh_webhook_router, prefix="/api")

    # Employee knowledge base
    from .knowledge import router as knowledge_router
    from app.models.knowledge import KnowledgeDocument  # noqa: F401
    app.include_router(knowledge_router, prefix="/api", dependencies=protected)

    # Живое прослушивание аудио салонов. Намеренно БЕЗ `protected`: WebSocket-
    # маршруты не проходят через HTTP-зависимость get_current_user (у неё
    # Request, а не WebSocket), поэтому авторизуются внутри — агент по токену
    # салона, слушатель по сессии + праву salon-audio. GET-статус несёт своё
    # require_permission.
    from .audio import create_audio_router
    app.include_router(create_audio_router(), prefix="/api")

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

    # Split-tunnel VPN (subscription, server selection, per-function routing)
    from .vpn import create_vpn_router

    app.include_router(
        create_vpn_router(),
        prefix="/api",
        dependencies=protected,
    )

    # Настройки и диагностика бота пошива (сторонний бот, Агбис -> amoCRM)
    from .poshiv_bot import create_poshiv_bot_router

    app.include_router(
        create_poshiv_bot_router(),
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

    # index.html references the *currently* hashed asset filenames, so it must
    # always be revalidated (no-cache) — otherwise a stale cached index.html
    # from a previous deploy could point at JS/CSS files that no longer exist.
    # Everything under dist/assets/ is content-hashed by Vite (a filename only
    # ever refers to one immutable set of bytes), so those are safe to cache
    # for a year with no revalidation at all.
    def _index_response() -> HTMLResponse:
        index_path = frontend_path / "index.html"
        if not index_path.exists():
            return Response(status_code=404)
        return HTMLResponse(
            index_path.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-cache"},
        )

    def _asset_response(file_path: Path) -> FileResponse:
        headers = (
            {"Cache-Control": "public, max-age=31536000, immutable"}
            if "assets" in file_path.parts
            else None
        )
        return FileResponse(str(file_path), headers=headers)

    @app.get("/admin", include_in_schema=False)
    async def admin_root(request: Request):
        return _index_response()

    @app.get("/admin/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str, request: Request):
        file_path = frontend_path / full_path
        if file_path.is_file():
            return _asset_response(file_path)
        # Don't fall back to SPA for static asset requests (e.g. sw.js, *.png)
        if "." in Path(full_path).name:
            return Response(status_code=404)
        return _index_response()

    @app.get("/manifest.json", include_in_schema=False)
    async def manifest_json():
        file_path = frontend_path / "manifest.json"
        if file_path.is_file():
            return FileResponse(str(file_path))
        return Response(status_code=404)

    @app.get("/icons/{filename}", include_in_schema=False)
    async def pwa_icons(filename: str):
        file_path = frontend_path / "icons" / filename
        if file_path.is_file():
            return FileResponse(str(file_path))
        return Response(status_code=404)

    @app.get("/login", include_in_schema=False)
    async def login_root(request: Request):
        return _index_response()

    @app.get("/employee", include_in_schema=False)
    async def employee_root(request: Request):
        return _index_response()

    @app.get("/employee/{full_path:path}", include_in_schema=False)
    async def employee_spa_fallback(full_path: str, request: Request):
        file_path = frontend_path / full_path
        if file_path.is_file():
            return _asset_response(file_path)
        # Don't fall back to SPA for static asset requests
        if "." in Path(full_path).name:
            return Response(status_code=404)
        return _index_response()

    if telegram_app is not None:

        @app.post("/webhook")
        async def webhook(request: Request):
            data = await request.json()
            update = Update.de_json(data, telegram_app.bot)
            await telegram_app.process_update(update)
            return {"status": "ok"}

    return app
