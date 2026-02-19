"""Payroll calculation service - combines Excel, Firebird, advances and bonuses."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from app.settings import settings
from app.data.sales_plans_repository import SalesPlansRepository, get_sales_plans_repository
from app.services.firebird_service import FirebirdService, get_firebird_service

logger = logging.getLogger(__name__)

# Russian month names -> month number
MONTH_NAMES = {
    "ЯНВАРЬ": 1, "ФЕВРАЛЬ": 2, "МАРТ": 3, "АПРЕЛЬ": 4,
    "МАЙ": 5, "ИЮНЬ": 6, "ИЮЛЬ": 7, "АВГУСТ": 8,
    "СЕНТЯБРЬ": 9, "ОКТЯБРЬ": 10, "НОЯБРЬ": 11, "ДЕКАБРЬ": 12,
}

# Commission rates
REPAIR_RATE_HIGH = 0.02
REPAIR_RATE_LOW = 0.01
COSMETICS_RATE_HIGH = 0.08
COSMETICS_RATE_LOW = 0.05
SHOES_RATE_HIGH = 0.05
SHOES_RATE_LOW = 0.03
PLAN_THRESHOLD = 0.80

CODE_RE = re.compile(r"(\d{4})$")


def _extract_code(name: str | None) -> str | None:
    """Extract 4-digit code from end of name string like 'Имя 1234'."""
    m = CODE_RE.search((name or "").strip())
    return m.group(1) if m else None


def _parse_dt(v) -> datetime:
    """Robust datetime parser supporting ISO strings, space-separated, timestamps."""
    if isinstance(v, datetime):
        return v
    if v is None:
        return datetime(1970, 1, 1)
    if isinstance(v, (int, float)):
        ts = float(v)
        if ts > 10_000_000_000:
            ts /= 1000.0
        return datetime.fromtimestamp(ts)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return datetime(1970, 1, 1)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            try:
                return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return datetime(1970, 1, 1)
    return datetime(1970, 1, 1)


def _dt_field(r: dict) -> Any:
    return r.get("date") or r.get("timestamp") or r.get("created_at") or r.get("createdAt")


@dataclass
class PayrollRow:
    employee_code: str
    employee_name: str
    base_salary: float

    repair_sales: float
    cosmetics_sales: float
    shoes_sales: float

    repair_plan: float
    cosmetics_plan: float
    shoes_plan: float

    repair_fulfillment: float
    cosmetics_fulfillment: float
    shoes_fulfillment: float

    repair_rate: float
    cosmetics_rate: float
    shoes_rate: float

    repair_commission: float
    cosmetics_commission: float
    shoes_commission: float

    bonuses: float  # from bonuses_penalties.json
    excel_bonus: float  # from Excel column BW
    penalties: float
    advances: float
    ignore_kpi: bool  # if True, commissions were zeroed
    shoes_orders: list  # unique order numbers (DOC_NUM) for shoes sales

    total_commission: float
    total_gross: float
    total_deductions: float
    total_net: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "employee_code": self.employee_code,
            "employee_name": self.employee_name,
            "base_salary": self.base_salary,
            "repair_sales": self.repair_sales,
            "cosmetics_sales": self.cosmetics_sales,
            "shoes_sales": self.shoes_sales,
            "repair_plan": self.repair_plan,
            "cosmetics_plan": self.cosmetics_plan,
            "shoes_plan": self.shoes_plan,
            "repair_fulfillment": self.repair_fulfillment,
            "cosmetics_fulfillment": self.cosmetics_fulfillment,
            "shoes_fulfillment": self.shoes_fulfillment,
            "repair_rate": self.repair_rate,
            "cosmetics_rate": self.cosmetics_rate,
            "shoes_rate": self.shoes_rate,
            "repair_commission": self.repair_commission,
            "cosmetics_commission": self.cosmetics_commission,
            "shoes_commission": self.shoes_commission,
            "bonuses": self.bonuses,
            "excel_bonus": self.excel_bonus,
            "penalties": self.penalties,
            "advances": self.advances,
            "ignore_kpi": self.ignore_kpi,
            "shoes_orders": self.shoes_orders,
            "total_commission": self.total_commission,
            "total_gross": self.total_gross,
            "total_deductions": self.total_deductions,
            "total_net": self.total_net,
        }


class PayrollService:
    def __init__(
        self,
        excel_path: str | Path | None = None,
        firebird_service: FirebirdService | None = None,
        plans_repo: SalesPlansRepository | None = None,
        advance_requests_file: str | None = None,
        bonuses_penalties_file: str | None = None,
        users_file: str | None = None,
    ) -> None:
        self.excel_path = Path(excel_path or settings.payroll_excel_file)
        self.firebird = firebird_service or get_firebird_service()
        self.plans_repo = plans_repo or get_sales_plans_repository()
        self.advance_requests_file = Path(advance_requests_file or settings.advance_requests_file)
        self.bonuses_penalties_file = Path(bonuses_penalties_file or settings.bonuses_penalties_file)
        self.users_file = Path(users_file or settings.users_file)

        # user_id -> employee_code, full_name -> employee_code
        self._user_id_to_code: dict[str, str] = {}
        self._full_name_to_code: dict[str, str] = {}
        self._load_user_mappings()

    def _load_user_mappings(self) -> None:
        """Build lookup maps from user.json: user_id -> code, full_name -> code."""
        if not self.users_file.exists():
            logger.warning(f"users file not found: {self.users_file}")
            return
        try:
            users = json.loads(self.users_file.read_text(encoding="utf-8"))
            for user_id, data in users.items():
                name = data.get("name", "")       # "Вера 0102"
                full_name = data.get("full_name", "")  # "Кочетова Вера Алексеевна"
                code = _extract_code(name)
                if code:
                    self._user_id_to_code[str(user_id)] = code
                    if full_name:
                        self._full_name_to_code[full_name.strip().lower()] = code
            logger.info(f"Loaded {len(self._user_id_to_code)} user mappings")
        except Exception as e:
            logger.error(f"Error loading user mappings: {e}")

    # ------------------------------------------------------------------ #
    # Excel                                                                #
    # ------------------------------------------------------------------ #

    def list_months(self) -> list[str]:
        """Return sheet names matching Russian month names."""
        if not self.excel_path.exists():
            logger.warning(f"Excel file not found: {self.excel_path}")
            return []
        try:
            wb = load_workbook(self.excel_path, read_only=True, data_only=True)
            months = [s.upper() for s in wb.sheetnames if s.strip().upper() in MONTH_NAMES]
            wb.close()
            return months
        except Exception as e:
            logger.error(f"Error listing months: {e}")
            return []

    def _get_employees_from_excel(self, month: str) -> list[dict[str, Any]]:
        """
        Read employees from Excel sheet.
        A3:A21   - name with code (e.g. "Вера 0102")
        AU3:AU21 - base salary
        BW3:BW21 - bonus from Excel
        """
        if not self.excel_path.exists():
            return []
        try:
            wb = load_workbook(self.excel_path, data_only=True)
            sheet_name = next(
                (s for s in wb.sheetnames if s.strip().upper() == month.strip().upper()),
                None,
            )
            if not sheet_name:
                logger.warning(f"Sheet '{month}' not found. Available: {wb.sheetnames}")
                return []

            ws = wb[sheet_name]
            employees = []
            for row in range(3, 22):  # rows 3..21
                name = ws[f"A{row}"].value
                oklad = ws[f"AU{row}"].value
                excel_bonus = ws[f"BW{row}"].value
                if not name:
                    continue
                code = _extract_code(str(name))
                if not code:
                    continue
                try:
                    salary = float(oklad or 0)
                except (TypeError, ValueError):
                    salary = 0.0
                try:
                    bonus = float(excel_bonus or 0)
                except (TypeError, ValueError):
                    bonus = 0.0
                employees.append({
                    "name": str(name).strip(),
                    "code": code,
                    "salary": salary,
                    "excel_bonus": bonus,
                })

            wb.close()
            return employees
        except Exception as e:
            logger.error(f"Error reading Excel sheet '{month}': {e}")
            return []

    # ------------------------------------------------------------------ #
    # Advances                                                             #
    # ------------------------------------------------------------------ #

    def _get_advances_after_last_salary(self) -> dict[str, float]:
        """
        Rule:
        - Find the LAST record with payout_type == "Зарплата" for each employee
        - Sum ALL payout_type == "Аванс" records that are AFTER that date
          (regardless of month - these are unpaid advances that need to be deducted)
        """
        if not self.advance_requests_file.exists():
            return {}
        try:
            data = json.loads(self.advance_requests_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Error reading advance requests: {e}")
            return {}

        # Group by employee code (code is at end of "name" field)
        ops: dict[str, list[dict]] = {}
        for row in data:
            code = _extract_code(row.get("name"))
            if not code:
                # Fallback: look up code via user_id
                code = self._user_id_to_code.get(str(row.get("user_id", "")))
            if code:
                ops.setdefault(code, []).append(row)

        out: dict[str, float] = {}
        for code, items in ops.items():
            items_sorted = sorted(items, key=lambda r: _parse_dt(_dt_field(r)))

            # Find last salary payment
            last_salary_dt: datetime | None = None
            for r in items_sorted:
                if r.get("payout_type") == "Зарплата":
                    last_salary_dt = _parse_dt(_dt_field(r))

            if last_salary_dt is None:
                # No salary payment yet - sum ALL advances
                total = sum(
                    float(r.get("amount") or 0)
                    for r in items_sorted
                    if r.get("payout_type") == "Аванс"
                )
                out[code] = total
                continue

            # Sum ALL advances after last salary (no month filter)
            total = 0.0
            for r in items_sorted:
                if r.get("payout_type") != "Аванс":
                    continue
                dt = _parse_dt(_dt_field(r))
                if dt <= last_salary_dt:
                    continue
                total += float(r.get("amount") or 0)

            out[code] = total

        return out

    # ------------------------------------------------------------------ #
    # Bonuses / Penalties                                                  #
    # ------------------------------------------------------------------ #

    def _get_bonuses_penalties_for_month(
        self, year: int, month: int
    ) -> tuple[dict[str, float], dict[str, float]]:
        """
        Return ({code: bonus_sum}, {code: penalty_sum}) for target month.
        bonuses_penalties.json uses employee_id (Telegram user_id) and full_name
        without 4-digit code, so we map via user.json.
        """
        if not self.bonuses_penalties_file.exists():
            return {}, {}
        try:
            data = json.loads(self.bonuses_penalties_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Error reading bonuses/penalties: {e}")
            return {}, {}

        bonuses: dict[str, float] = {}
        penalties: dict[str, float] = {}

        for r in data:
            # Try to resolve code: first via employee_id, then via full_name
            code = self._user_id_to_code.get(str(r.get("employee_id", "")))
            if not code:
                full_name = (r.get("name") or "").strip().lower()
                code = self._full_name_to_code.get(full_name)
            if not code:
                # Last resort: direct code extraction (handles future format changes)
                code = _extract_code(r.get("name"))
            if not code:
                continue

            # Filter by month
            dt = _parse_dt(r.get("date"))
            if dt.year != year or dt.month != month:
                continue

            amt = float(r.get("amount") or 0)
            if r.get("type") == "bonus":
                bonuses[code] = bonuses.get(code, 0.0) + amt
            elif r.get("type") == "penalty":
                penalties[code] = penalties.get(code, 0.0) + amt

        return bonuses, penalties

    # ------------------------------------------------------------------ #
    # Commission                                                           #
    # ------------------------------------------------------------------ #

    def _commission(
        self, sales: float, plan: float, rate_hi: float, rate_lo: float
    ) -> tuple[float, float, float]:
        """Returns (fulfillment_pct, rate_applied, commission_amount)."""
        if plan and plan > 0:
            fulfillment = sales / plan
            rate = rate_hi if fulfillment >= PLAN_THRESHOLD else rate_lo
        else:
            fulfillment = 0.0
            rate = rate_lo
        return fulfillment, rate, sales * rate

    # ------------------------------------------------------------------ #
    # Main calculation                                                     #
    # ------------------------------------------------------------------ #

    async def calculate_payroll(
        self, month: str, year: int | None = None
    ) -> list[PayrollRow]:
        month = month.strip().upper()
        month_num = MONTH_NAMES.get(month)
        if not month_num:
            logger.error(f"Unknown month: {month}")
            return []

        if year is None:
            year = datetime.now().year

        # Load all data sources
        employees = self._get_employees_from_excel(month)
        if not employees:
            logger.warning(f"No employees found for month {month}")
            return []

        try:
            sales_data = self.firebird.get_all_sales(year, month_num)
        except Exception as e:
            logger.error(f"Firebird error: {e}")
            sales_data = {}

        advances_map = self._get_advances_after_last_salary()
        bonuses_map, penalties_map = self._get_bonuses_penalties_for_month(year, month_num)
        plans_map = self.plans_repo.get_plans_map()

        results = []
        for emp in employees:
            code = emp["code"]
            name = emp["name"]
            base_salary = emp["salary"]
            excel_bonus = emp.get("excel_bonus", 0.0)

            emp_sales = sales_data.get(code, {})
            repair_sales = emp_sales.get("repair", 0.0)
            cosmetics_sales = emp_sales.get("cosmetics", 0.0)
            shoes_sales = emp_sales.get("shoes", 0.0)
            shoes_orders = emp_sales.get("shoes_orders", [])

            plan = plans_map.get(code)
            repair_plan = plan.repair_plan if plan else 0.0
            cosmetics_plan = plan.cosmetics_plan if plan else 0.0
            shoes_plan = plan.shoes_plan if plan else 0.0
            ignore_kpi = plan.ignore_kpi if plan else False

            repair_fulfillment, repair_rate, repair_commission = self._commission(
                repair_sales, repair_plan, REPAIR_RATE_HIGH, REPAIR_RATE_LOW
            )
            cosmetics_fulfillment, cosmetics_rate, cosmetics_commission = self._commission(
                cosmetics_sales, cosmetics_plan, COSMETICS_RATE_HIGH, COSMETICS_RATE_LOW
            )
            shoes_fulfillment, shoes_rate, shoes_commission = self._commission(
                shoes_sales, shoes_plan, SHOES_RATE_HIGH, SHOES_RATE_LOW
            )

            # If ignore_kpi is set, zero out all commissions
            if ignore_kpi:
                repair_commission = 0.0
                cosmetics_commission = 0.0
                shoes_commission = 0.0

            bonuses = bonuses_map.get(code, 0.0)
            penalties = penalties_map.get(code, 0.0)
            advances = advances_map.get(code, 0.0)

            total_commission = repair_commission + cosmetics_commission + shoes_commission
            total_gross = base_salary + total_commission + bonuses + excel_bonus
            total_deductions = advances + penalties
            total_net = total_gross - total_deductions

            results.append(PayrollRow(
                employee_code=code,
                employee_name=name,
                base_salary=base_salary,
                repair_sales=repair_sales,
                cosmetics_sales=cosmetics_sales,
                shoes_sales=shoes_sales,
                repair_plan=repair_plan,
                cosmetics_plan=cosmetics_plan,
                shoes_plan=shoes_plan,
                repair_fulfillment=repair_fulfillment,
                cosmetics_fulfillment=cosmetics_fulfillment,
                shoes_fulfillment=shoes_fulfillment,
                repair_rate=repair_rate,
                cosmetics_rate=cosmetics_rate,
                shoes_rate=shoes_rate,
                repair_commission=repair_commission,
                cosmetics_commission=cosmetics_commission,
                shoes_commission=shoes_commission,
                bonuses=bonuses,
                excel_bonus=excel_bonus,
                penalties=penalties,
                advances=advances,
                ignore_kpi=ignore_kpi,
                shoes_orders=shoes_orders,
                total_commission=total_commission,
                total_gross=total_gross,
                total_deductions=total_deductions,
                total_net=total_net,
            ))

        return results

    async def get_employee_details(
        self, employee_code: str, month: str, year: int | None = None
    ) -> PayrollRow | None:
        rows = await self.calculate_payroll(month, year)
        for row in rows:
            if row.employee_code == employee_code:
                return row
        return None


_payroll_service: PayrollService | None = None


def get_payroll_service() -> PayrollService:
    global _payroll_service
    if _payroll_service is None:
        _payroll_service = PayrollService()
    return _payroll_service
