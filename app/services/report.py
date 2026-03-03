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
        return f"{int(round(v))} \u20bd"

    def fmt_rate(rate: float, hi: float, lo: float) -> str:
        pct = int(round(rate * 100))
        if abs(rate - hi) < 1e-6:
            return f"{pct}%, план выполнен"
        if abs(rate - lo) < 1e-6:
            return f"{pct}%, план не выполнен"
        if rate == 0.0:
            return "не начисляется"
        return f"{pct}%"

    total_bonus = row.bonuses + row.excel_bonus

    return [
        [
            ("ЗАГОЛОВОК ОТЧЁТА", ""),
            ("Сотрудник", row.employee_name),
            ("Период", month),
            ("Оклад", fmt(row.base_salary)),
        ],
        [
            ("KPI", ""),
            ("Ремонт", fmt_rate(row.repair_rate, 0.02, 0.01)),
            ("Косметика", fmt_rate(row.cosmetics_rate, 0.08, 0.05)),
            ("Обувь", fmt(row.shoes_commission)),
        ],
        [
            ("НАЧИСЛЕНИЯ И УДЕРЖАНИЯ", ""),
            ("Оклад", fmt(row.base_salary)),
            ("Ремонт", fmt(row.repair_commission)),
            ("Косметика", fmt(row.cosmetics_commission)),
            ("Обувь", fmt(row.shoes_commission)),
            ("Бонус", fmt(total_bonus)),
            ("ИТОГО", fmt(row.total_gross)),
            ("Удержание", fmt(row.penalties)),
            ("Аванс", fmt(row.advances)),
            ("К выплате", fmt(row.total_net)),
        ],
    ]
