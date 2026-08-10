"""Route a payout-form employee selection to whichever system actually
computes that employee's pay, so the admin sees a total salary + к выплате
figure without re-deriving it by hand for four different systems:

    мастер (Мастер по ...)  -> masters_service (Firebird commission report)
    курьер (Курьер)         -> the courier salary accrual saved for this month
    менеджер (Менеджер ...) -> the manager salary accrual saved for this month
    everyone else           -> payroll_service (Excel schedule + Firebird sales)

The "авансы с последней зарплаты" figure is the one already-unified concept
across all four (PayoutRepository.advances_since_last_salary, keyed by the
employee's own bot id) -- that part does not need routing. This reuses the
sync repository method added for the masters page rather than
app.api.manager_salary's async twin of the same definition, so that this
module -- called from a plain API handler, not from the bot process -- never
has to import the app.api package (and, transitively, the Telegram
application factory) just to compute a number.

Manager/courier salary is not something this can compute live: their oklad
and KPI actuals are entered by hand into the accrual form, not derived from
Firebird/Excel. So for those two roles this reads the most recent saved
accrual for the current calendar period rather than computing anything, and
says so plainly when none exists yet -- a guess here would misstate a real
payroll figure.
"""
from __future__ import annotations

import asyncio
import calendar
from datetime import date

from app.data.employee_repository import EmployeeRepository
from app.data.payout_repository import PayoutRepository

_MASTER_HINT = "мастер"
_COURIER_HINT = "курьер"
_MANAGER_HINT = "менеджер"


def _month_end(year: int, month: int) -> date:
    """Last day to include for this period — today itself for the current
    (still-running) month, since a future date would just clamp anyway; the
    calendar month-end for any past period."""
    today = date.today()
    if (year, month) == (today.year, today.month):
        return today
    return date(year, month, calendar.monthrange(year, month)[1])

# Same budget app/api/masters.py uses for the identical fetch_works() call --
# see run_with_timeout there for why a bare asyncio.wait_for isn't enough on
# a contended Firebird connection.
_MASTER_LOOKUP_TIMEOUT_S = 55


def _position_role(position: str) -> str:
    p = (position or "").strip().lower()
    if _MASTER_HINT in p:
        return "master"
    if _COURIER_HINT in p:
        return "courier"
    if _MANAGER_HINT in p:
        return "manager"
    return "staff"


async def _master_gross(employee_id: str, year: int, month: int) -> tuple[float | None, str | None]:
    from app.services import masters_service
    from app.services.firebird_service import run_with_timeout

    if not masters_service.FIREBIRD_AVAILABLE:
        return None, "Firebird недоступен: драйвер fdb не установлен."
    month_start = date(year, month, 1)
    month_end = _month_end(year, month)
    try:
        result = await run_with_timeout(
            masters_service.fetch_works,
            date_from=month_start,
            date_to=month_end,
            timeout=_MASTER_LOOKUP_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        stale = masters_service.fetch_works_stale(month_start, month_end)
        if stale is None:
            return None, "Firebird не отвечает — попробуйте ещё раз позже."
        result, _age = stale
    except Exception as exc:
        return None, f"Не удалось получить данные из Firebird: {exc}"

    summary = result.get("salary_summary") or []
    row = masters_service.find_master_salary_row(employee_id, summary)
    if row is None:
        return None, f"Не найдено начислений за {month:02d}.{year} в отчёте по мастерам."
    return float(row.get("total_salary") or 0), None


def _accrual_gross(kind: str, employee_id: str, year: int, month: int) -> tuple[float | None, str | None]:
    period = f"{year:04d}-{month:02d}"
    if kind == "courier":
        from app.data.courier_salary_repository import get_courier_salary_repository
        repo = get_courier_salary_repository()
        page = "странице зарплаты курьера"
    else:
        from app.data.manager_salary_repository import get_manager_salary_repository
        repo = get_manager_salary_repository()
        page = "странице зарплаты менеджера"

    rows = repo.list(employee_code=str(employee_id), period=period, limit=1)
    if not rows:
        return None, f"Нет начисления за {period} — сформируйте его на {page}."
    gross = (rows[0].get("result") or {}).get("gross")
    return (float(gross) if gross is not None else None), None


async def _staff_gross(employee, year: int, month: int) -> tuple[float | None, str | None]:
    from app.services.payroll_service import CODE_RE, MONTH_NAMES, PayrollService

    code_match = CODE_RE.search((employee.name or "").strip())
    if not code_match:
        return None, "Не удалось определить код сотрудника (имя без 4 цифр в конце)."
    code = code_match.group(1)

    month_name = next((k for k, v in MONTH_NAMES.items() if v == month), None)
    if month_name is None:  # unreachable given MONTH_NAMES covers 1-12, kept honest anyway
        return None, "Не удалось определить выбранный месяц."

    service = PayrollService()
    row = await service.get_employee_details(code, month_name, year)
    if row is None:
        return None, f"Нет данных за {month_name.title()} в Excel-графике для кода {code}."
    return float(row.total_gross), None


async def get_salary_context(employee_id: str, year: int | None = None, month: int | None = None) -> dict:
    """{found, position, role, total_salary, advances_since_last_salary,
    to_pay, note} for the payout form. `total_salary`/`to_pay` are None (with
    `note` explaining why) when the employee's role has nothing computed for
    the requested period yet -- the caller should show that as "not
    available", never substitute a guess.

    `year`/`month` default to the current calendar month -- but payouts are
    often created a few days into the new month for the *previous* month's
    salary, so the caller (the payout form) lets the admin override this
    instead of it always silently meaning "right now"."""
    employee = EmployeeRepository().get_employee(employee_id)
    if employee is None:
        return {"found": False}

    today = date.today()
    year = year or today.year
    month = month or today.month

    advances = PayoutRepository().advances_since_last_salary(employee_id)

    role = _position_role(employee.position)
    if role == "master":
        total_salary, note = await _master_gross(employee_id, year, month)
    elif role in ("courier", "manager"):
        total_salary, note = _accrual_gross(role, employee_id, year, month)
    else:
        total_salary, note = await _staff_gross(employee, year, month)

    to_pay = round(total_salary - advances["total"], 2) if total_salary is not None else None

    return {
        "found": True,
        "employee_id": str(employee_id),
        "position": employee.position or "",
        "role": role,
        "total_salary": total_salary,
        "advances_since_last_salary": advances["total"],
        "advances_since": advances.get("since"),
        "to_pay": to_pay,
        "note": note,
    }
