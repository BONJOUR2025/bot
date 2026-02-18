"""Payroll calculation service - combines all data sources."""
from __future__ import annotations

import json
import logging
import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.settings import settings
from app.data.sales_plans_repository import (
    SalesPlansRepository,
    get_sales_plans_repository,
)
from app.services.firebird_service import FirebirdService, get_firebird_service

logger = logging.getLogger(__name__)

# Russian month names to number mapping
MONTH_NAMES = {
    "ЯНВАРЬ": 1, "ФЕВРАЛЬ": 2, "МАРТ": 3, "АПРЕЛЬ": 4,
    "МАЙ": 5, "ИЮНЬ": 6, "ИЮЛЬ": 7, "АВГУСТ": 8,
    "СЕНТЯБРЬ": 9, "ОКТЯБРЬ": 10, "НОЯБРЬ": 11, "ДЕКАБРЬ": 12,
}

# Percentage rates based on plan fulfillment
REPAIR_RATE_HIGH = 0.02  # 2% if >= 80% of plan
REPAIR_RATE_LOW = 0.01   # 1% if < 80% of plan
COSMETICS_RATE_HIGH = 0.08  # 8% if >= 80% of plan
COSMETICS_RATE_LOW = 0.05   # 5% if < 80% of plan
SHOES_RATE_HIGH = 0.05  # 5% if >= 80% of plan
SHOES_RATE_LOW = 0.03   # 3% if < 80% of plan
PLAN_THRESHOLD = 0.80  # 80% threshold


@dataclass
class PayrollRow:
    """Calculated payroll row for an employee."""
    employee_code: str
    employee_name: str
    base_salary: float  # Оклад

    # Sales amounts
    repair_sales: float
    cosmetics_sales: float
    shoes_sales: float

    # Plans
    repair_plan: float
    cosmetics_plan: float
    shoes_plan: float

    # Plan fulfillment percentages
    repair_fulfillment: float
    cosmetics_fulfillment: float
    shoes_fulfillment: float

    # Commission rates applied
    repair_rate: float
    cosmetics_rate: float
    shoes_rate: float

    # Commission amounts
    repair_commission: float
    cosmetics_commission: float
    shoes_commission: float

    # Bonuses and deductions
    bonuses: float
    penalties: float
    advances: float

    # Totals
    total_commission: float
    total_gross: float  # Оклад + комиссии + бонусы
    total_deductions: float  # Авансы + удержания
    total_net: float  # К выплате

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
            "penalties": self.penalties,
            "advances": self.advances,
            "total_commission": self.total_commission,
            "total_gross": self.total_gross,
            "total_deductions": self.total_deductions,
            "total_net": self.total_net,
        }


class PayrollService:
    """Service for calculating employee payroll."""

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
        self.advance_requests_file = Path(
            advance_requests_file or settings.advance_requests_file
        )
        self.bonuses_penalties_file = Path(
            bonuses_penalties_file or settings.bonuses_penalties_file
        )
        self.users_file = Path(users_file or settings.users_file)
        self._excel_cache: dict[str, pd.DataFrame] = {}

        # Mappings for employee lookup
        self._code_to_user_id: dict[str, str] = {}
        self._user_id_to_code: dict[str, str] = {}
        self._full_name_to_code: dict[str, str] = {}
        self._load_user_mappings()

    def _load_user_mappings(self) -> None:
        """Load user.json and build mappings between code, user_id, full_name."""
        if not self.users_file.exists():
            logger.warning(f"Users file not found: {self.users_file}")
            return

        try:
            with open(self.users_file, "r", encoding="utf-8") as f:
                users = json.load(f)

            for user_id, data in users.items():
                name = data.get("name", "")  # "Вера 0102"
                full_name = data.get("full_name", "")  # "Кочетова Вера Алексеевна"

                code = self._extract_employee_code(name)
                if code:
                    self._code_to_user_id[code] = user_id
                    self._user_id_to_code[user_id] = code
                    if full_name:
                        # Normalize full name for lookup
                        self._full_name_to_code[full_name.strip().lower()] = code

            logger.info(f"Loaded {len(self._code_to_user_id)} employee mappings")
        except Exception as e:
            logger.error(f"Error loading user mappings: {e}")

    def _extract_employee_code(self, name: str) -> str | None:
        """Extract 4-digit code from employee name like 'Имя 1234'."""
        if not name:
            return None
        name = str(name).strip()
        match = re.search(r'\b(\d{4})\b', name)
        if match:
            return match.group(1)
        return None

    def _get_code_from_user_id(self, user_id: str) -> str | None:
        """Get employee code from Telegram user_id."""
        return self._user_id_to_code.get(str(user_id))

    def _get_code_from_full_name(self, full_name: str) -> str | None:
        """Get employee code from full name."""
        if not full_name:
            return None
        return self._full_name_to_code.get(full_name.strip().lower())

    def list_months(self) -> list[str]:
        """List available months from Excel file."""
        if not self.excel_path.exists():
            logger.warning(f"Excel file not found: {self.excel_path}")
            return []
        try:
            xl = pd.ExcelFile(self.excel_path)
            months = []
            for sheet in xl.sheet_names:
                sheet_upper = sheet.strip().upper()
                if sheet_upper in MONTH_NAMES:
                    months.append(sheet_upper)
            return months
        except Exception as e:
            logger.error(f"Error listing months: {e}")
            return []

    def _load_excel_sheet(self, month: str) -> pd.DataFrame | None:
        """Load Excel sheet for a month."""
        month = month.strip().upper()
        if month in self._excel_cache:
            return self._excel_cache[month]

        if not self.excel_path.exists():
            return None

        try:
            df = pd.read_excel(
                self.excel_path,
                sheet_name=month,
                header=None,  # No header, we'll use row indexes
            )
            self._excel_cache[month] = df
            return df
        except Exception as e:
            logger.error(f"Error loading Excel sheet {month}: {e}")
            return None

    def _get_employees_from_excel(self, month: str) -> list[dict[str, Any]]:
        """
        Get employee names and salaries from Excel.
        Names: A3:A21 (row index 2-20, col 0)
        Salaries: AU3:AU21 (row index 2-20, col 46 = 'AU')
        """
        df = self._load_excel_sheet(month)
        if df is None:
            return []

        employees = []
        # AU column is index 46 (A=0, B=1, ..., Z=25, AA=26, ..., AU=46)
        salary_col = 46  # AU

        for row_idx in range(2, 21):  # Rows 3-21 (0-indexed: 2-20)
            try:
                name = df.iloc[row_idx, 0]  # Column A
                if pd.isna(name) or not str(name).strip():
                    continue

                name = str(name).strip()
                code = self._extract_employee_code(name)
                if not code:
                    continue

                salary = 0.0
                try:
                    salary_val = df.iloc[row_idx, salary_col]
                    if not pd.isna(salary_val):
                        salary = float(salary_val)
                except (IndexError, ValueError):
                    pass

                employees.append({
                    "name": name,
                    "code": code,
                    "salary": salary,
                })
            except IndexError:
                continue

        return employees

    def _get_month_date_range(self, month: str, year: int | None = None) -> tuple[date, date]:
        """Get date range for a month."""
        month_num = MONTH_NAMES.get(month.strip().upper())
        if not month_num:
            raise ValueError(f"Unknown month: {month}")

        if year is None:
            year = datetime.now().year

        first_day = date(year, month_num, 1)
        last_day = date(year, month_num, monthrange(year, month_num)[1])
        return first_day, last_day

    def _load_advance_requests(self) -> list[dict[str, Any]]:
        """Load advance requests from JSON file."""
        if not self.advance_requests_file.exists():
            return []
        try:
            with open(self.advance_requests_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Error loading advance requests: {e}")
            return []

    def _parse_timestamp(self, ts: str) -> datetime | None:
        """Parse timestamp from various formats."""
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace(" ", "T"))
        except:
            try:
                return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            except:
                return None

    def _get_advances_for_period(
        self, employee_code: str, date_from: date, date_to: date
    ) -> float:
        """
        Get total advances for an employee in a period.
        Sums all advances with status "Выплачено" in the date range.
        """
        requests = self._load_advance_requests()

        total = 0.0
        for req in requests:
            # Match by employee code from name field
            name = req.get("name", "")
            code = self._extract_employee_code(name)

            # Also try matching by user_id
            if not code or code != employee_code:
                user_id = req.get("user_id", "")
                code = self._get_code_from_user_id(user_id)

            if code != employee_code:
                continue

            # Only count advances
            if req.get("payout_type") != "Аванс":
                continue

            # Only count paid advances
            if req.get("status") != "Выплачено":
                continue

            # Check date
            ts = self._parse_timestamp(req.get("timestamp", ""))
            if not ts:
                continue

            if date_from <= ts.date() <= date_to:
                total += float(req.get("amount", 0))

        return total

    def _load_bonuses_penalties(self) -> list[dict[str, Any]]:
        """Load bonuses and penalties from JSON file."""
        if not self.bonuses_penalties_file.exists():
            return []
        try:
            with open(self.bonuses_penalties_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Error loading bonuses/penalties: {e}")
            return []

    def _get_bonuses_penalties(
        self, employee_code: str, date_from: date, date_to: date
    ) -> tuple[float, float]:
        """
        Get bonuses and penalties for an employee in a period.
        Returns: (bonuses, penalties)
        """
        items = self._load_bonuses_penalties()

        bonuses = 0.0
        penalties = 0.0

        for item in items:
            # Try to match by employee_id (Telegram user_id)
            employee_id = item.get("employee_id", "")
            code = self._get_code_from_user_id(employee_id)

            # Also try matching by full name
            if not code:
                full_name = item.get("name", "")
                code = self._get_code_from_full_name(full_name)

            # Also try extracting code directly from name (if it has format "Имя ХХХХ")
            if not code:
                name = item.get("name", "")
                code = self._extract_employee_code(name)

            if code != employee_code:
                continue

            # Parse date
            date_str = item.get("date", "")
            try:
                item_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except:
                try:
                    item_date = datetime.fromisoformat(date_str).date()
                except:
                    continue

            if not (date_from <= item_date <= date_to):
                continue

            amount = float(item.get("amount", 0))
            item_type = item.get("type", "")

            if item_type == "bonus":
                bonuses += amount
            elif item_type == "penalty":
                penalties += amount

        return bonuses, penalties

    def _calculate_commission(
        self,
        sales: float,
        plan: float,
        rate_high: float,
        rate_low: float,
    ) -> tuple[float, float, float]:
        """
        Calculate commission based on plan fulfillment.
        Returns: (fulfillment_pct, rate_applied, commission_amount)
        """
        if plan <= 0:
            # No plan set - use low rate
            return 0.0, rate_low, sales * rate_low

        fulfillment = sales / plan
        if fulfillment >= PLAN_THRESHOLD:
            rate = rate_high
        else:
            rate = rate_low

        commission = sales * rate
        return fulfillment, rate, commission

    async def calculate_payroll(
        self, month: str, year: int | None = None
    ) -> list[PayrollRow]:
        """Calculate payroll for all employees for a given month."""
        month = month.strip().upper()

        # Get date range
        try:
            date_from, date_to = self._get_month_date_range(month, year)
        except ValueError as e:
            logger.error(f"Invalid month: {e}")
            return []

        # Get employees from Excel
        employees = self._get_employees_from_excel(month)
        if not employees:
            logger.warning(f"No employees found for month {month}")
            return []

        # Get sales data from Firebird
        try:
            sales_data = self.firebird.get_all_sales(date_from, date_to)
        except Exception as e:
            logger.error(f"Error getting sales data: {e}")
            sales_data = {}

        # Get plans
        plans_map = self.plans_repo.get_plans_map()

        results = []
        for emp in employees:
            code = emp["code"]
            name = emp["name"]
            base_salary = emp["salary"]

            # Get sales
            emp_sales = sales_data.get(code, {})
            repair_sales = emp_sales.get("repair", 0.0)
            cosmetics_sales = emp_sales.get("cosmetics", 0.0)
            shoes_sales = emp_sales.get("shoes", 0.0)

            # Get plan
            plan = plans_map.get(code)
            repair_plan = plan.repair_plan if plan else 0.0
            cosmetics_plan = plan.cosmetics_plan if plan else 0.0
            shoes_plan = plan.shoes_plan if plan else 0.0

            # Calculate commissions
            repair_fulfillment, repair_rate, repair_commission = self._calculate_commission(
                repair_sales, repair_plan, REPAIR_RATE_HIGH, REPAIR_RATE_LOW
            )
            cosmetics_fulfillment, cosmetics_rate, cosmetics_commission = self._calculate_commission(
                cosmetics_sales, cosmetics_plan, COSMETICS_RATE_HIGH, COSMETICS_RATE_LOW
            )
            shoes_fulfillment, shoes_rate, shoes_commission = self._calculate_commission(
                shoes_sales, shoes_plan, SHOES_RATE_HIGH, SHOES_RATE_LOW
            )

            # Get bonuses and penalties
            bonuses, penalties = self._get_bonuses_penalties(code, date_from, date_to)

            # Get advances
            advances = self._get_advances_for_period(code, date_from, date_to)

            # Calculate totals
            total_commission = repair_commission + cosmetics_commission + shoes_commission
            total_gross = base_salary + total_commission + bonuses
            total_deductions = advances + penalties
            total_net = total_gross - total_deductions

            row = PayrollRow(
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
                penalties=penalties,
                advances=advances,
                total_commission=total_commission,
                total_gross=total_gross,
                total_deductions=total_deductions,
                total_net=total_net,
            )
            results.append(row)

        return results

    async def get_employee_details(
        self, employee_code: str, month: str, year: int | None = None
    ) -> PayrollRow | None:
        """Get detailed payroll calculation for a single employee."""
        payroll = await self.calculate_payroll(month, year)
        for row in payroll:
            if row.employee_code == employee_code:
                return row
        return None


_payroll_service: PayrollService | None = None


def get_payroll_service() -> PayrollService:
    global _payroll_service
    if _payroll_service is None:
        _payroll_service = PayrollService()
    return _payroll_service
