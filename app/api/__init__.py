from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from telegram import Update

from ..config import TOKEN
from ..core.application import create_application
from .employees import create_employee_router
from .salary import create_salary_router
from .schedule import create_schedule_router
from .payouts import create_payout_router
from .birthdays import create_birthdays_router
from .telegram import create_telegram_router
from ..services.employee_service import EmployeeService, EmployeeAPIService
from ..services.salary_service import SalaryService
from ..services.schedule_service import ScheduleService
from ..services.payout_service import PayoutService
from ..services.birthday_service import BirthdayService
from ..services.vacation_service import VacationService
from ..services.adjustment_service import AdjustmentService
from .vacations import create_vacation_router
from .adjustments import create_adjustment_router


def create_app() -> FastAPI:
    app = FastAPI()

    telegram_app = None
    if TOKEN and TOKEN != "dummy":
        telegram_app = create_application()
    # Mount static files for admin UI
    app.mount("/static", StaticFiles(directory="static"), name="static")

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

    payout_service = PayoutService()
    app.include_router(create_payout_router(payout_service), prefix="/api")

    birthday_service = BirthdayService(employee_service._repo)
    app.include_router(create_birthdays_router(birthday_service), prefix="/api")

    vacation_service = VacationService()
    app.include_router(create_vacation_router(vacation_service), prefix="/api")

    adjustment_service = AdjustmentService()
    app.include_router(create_adjustment_router(adjustment_service), prefix="/api")

    app.include_router(create_telegram_router(employee_service._repo), prefix="/api")

    # Admin UI routes
    from .admin_ui import router as admin_router
    app.include_router(admin_router, include_in_schema=False)

    if telegram_app is not None:
        @app.post("/webhook")
        async def webhook(request: Request):
            data = await request.json()
            update = Update.de_json(data, telegram_app.bot)
            await telegram_app.process_update(update)
            return {"status": "ok"}

    return app
