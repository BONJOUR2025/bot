from __future__ import annotations

import pandas as pd
from pandas import DataFrame
from .excel import get_cell_comment


def generate_employee_report(
    employee_name: str, month: str, data: DataFrame, row_index: int
):
    """Возвращает структуру данных для отчёта по сотруднику."""

    def get_value(
        column: str,
        currency: bool = False,
        unit: str = "",
        round_value: bool = True,
    ):
        if column in data.columns:
            value = data.at[row_index, column]
            if pd.isna(value):
                return "Нет данных"
            if isinstance(value, str) and "error" in value.lower():
                return "Ошибка данных"
            try:
                value = float(value)
            except (ValueError, TypeError):
                return str(value)
            if round_value:
                value = int(round(value))
            if currency:
                return f"{value} ₽"
            if unit:
                return f"{value} {unit}"
            return str(value)
        return "Нет данных"

    def format_kpi(value, num1, text1, num2, text2):
        try:
            value = float(value)
        except (ValueError, TypeError):
            return "не начисляется"
        percent_value = value * 100
        if abs(value - num1) < 1e-6:
            return f"{int(percent_value)}%, {text1}"
        if abs(value - num2) < 1e-6:
            return f"{int(percent_value)}%, {text2}"
        return f"{int(percent_value)}%"

    return [
        [
            ("ЗАГОЛОВОК ОТЧЁТА", ""),
            ("Сотрудник", employee_name),
            ("Период", month),
            ("Основная ставка", get_value("ОСН", currency=True)),
            ("Основные смены", get_value("ОСН.")),
            ("Дополнительная ставка", get_value("ДОП", currency=True)),
            ("Дополнительные смены", get_value("ДОП.")),
        ],
        [
            ("KPI", ""),
            (
                "Ремонт",
                format_kpi(
                    get_value("Р", round_value=False),
                    0.01,
                    "план не выполнен",
                    0.02,
                    "план выполнен",
                ),
            ),
            (
                "Косметика",
                format_kpi(
                    get_value("К", round_value=False),
                    0.05,
                    "план не выполнен",
                    0.08,
                    "план выполнен",
                ),
            ),
            ("Обувь", get_value("О", currency=False, unit="₽/шт.")),
        ],
        [
            ("НАЧИСЛЕНИЯ И УДЕРЖАНИЯ", ""),
            ("Оклад", get_value("ОКЛАД", currency=True)),
            ("Ремонт", get_value("Ремонт", currency=True)),
            ("Косметика", get_value("Косметика", currency=True)),
            ("Обувь", get_value("Обувь", currency=True)),
            ("Аксессуары", get_value("Аксессуары", currency=True)),
            ("Ключи", get_value("Ключи", currency=True)),
            ("Тапки", get_value("Тапки", currency=True)),
            ("Цех", get_value("Цех", currency=True)),
            ("Бонус", get_value("Бонус", currency=True)),
            ("ИТОГО", get_value("ИТОГО", currency=True)),
            ("Удержание", get_value("Удержание", currency=True)),
            ("Аванс", get_value("Аванс", currency=True)),
            ("К выплате", get_value("К выплате", currency=True)),
        ],
        [
            ("ПОЯСНЕНИЕ НАЧИСЛЕНИЙ", ""),
            ("Аванс", get_cell_comment(month, row_index, "CM")),
            ("Удержание", get_cell_comment(month, row_index, "CI")),
            ("Бонус", get_cell_comment(month, row_index, "CA")),
        ],
    ]


def generate_employee_report_from_payroll(row, month: str) -> list:
    """Возвращает структуру отчёта из объекта PayrollRow (источник — SQL/Firebird)."""

    def fmt(v: float) -> str:
        """Форматирует число как рубли с пробелом-разделителем тысяч."""
        return f"{int(round(v)):,} \u20bd".replace(",", "\u202f")

    def fmt_kpi(sales: float, plan: float, fulfillment: float,
                rate: float, ignore_kpi: bool) -> str:
        """Строка KPI с деталями плана."""
        if ignore_kpi or plan <= 0:
            return "\u2014"  # —
        pct_rate = int(round(rate * 100))
        pct_fill = int(round(fulfillment * 100))
        if fulfillment >= 0.8:
            status = f"\u2705 {pct_rate}%, план выполнен"
            if sales > plan:
                extra = f"Перевыполнение: +{fmt(sales - plan)}"
            else:
                extra = f"Выполнение: {pct_fill}%"
        else:
            status = f"\u274c {pct_rate}%, план не выполнен"
            remaining = plan * 0.8 - sales
            extra = f"До 80%: {fmt(max(0.0, remaining))}"
        detail = f"План: {fmt(plan)}  Факт: {fmt(sales)}"
        return f"{status}\n{detail}\n{extra}"

    # ── Начисления (только из payroll/json) ──────────────────────
    bonus = row.bonuses  # только json-бонус, без excel_bonus
    итого = (
        row.base_salary
        + row.repair_commission
        + row.cosmetics_commission
        + row.shoes_commission
        + bonus
    )
    к_выплате = итого - row.penalties - row.advances

    kpi_repair = fmt_kpi(
        row.repair_sales, row.repair_plan,
        row.repair_fulfillment, row.repair_rate,
        row.ignore_kpi,
    )
    kpi_cosmetics = fmt_kpi(
        row.cosmetics_sales, row.cosmetics_plan,
        row.cosmetics_fulfillment, row.cosmetics_rate,
        row.ignore_kpi,
    )

    sections = [
        [
            ("ЗАГОЛОВОК ОТЧЁТА", ""),
            ("Сотрудник", row.employee_name),
            ("Период", month),
            ("Основная ставка", fmt(row.main_rate) if row.main_rate else "—"),
            ("Основные смены", str(int(row.main_shifts)) if row.main_shifts else "—"),
            ("Дополнительная ставка", fmt(row.extra_rate) if row.extra_rate else "—"),
            ("Дополнительные смены", str(int(row.extra_shifts)) if row.extra_shifts else "—"),
        ],
        [
            ("KPI", ""),
            ("Ремонт", kpi_repair),
            ("Косметика", kpi_cosmetics),
        ],
        [
            ("НАЧИСЛЕНИЯ И УДЕРЖАНИЯ", ""),
            ("Оклад", fmt(row.base_salary)),
            ("Ремонт", fmt(row.repair_commission)),
            ("Косметика", fmt(row.cosmetics_commission)),
            ("Обувь", fmt(row.shoes_commission)),
        ],
    ]

    if row.workshop_commission:
        sections[2].append(("Цех", fmt(row.workshop_commission)))

    sections[2].extend([
        ("Бонус", fmt(bonus)),
        ("ИТОГО", fmt(итого)),
        ("Удержание", fmt(row.penalties)),
        ("Аванс", fmt(row.advances)),
        ("К выплате", fmt(к_выплате)),
    ])

    return sections
