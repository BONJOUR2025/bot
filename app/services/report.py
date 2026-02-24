import pandas as pd
from pandas import DataFrame
from .excel import get_cell_comment
from ..utils.logger import log


def generate_employee_report(
    employee_name: str, month: str, data: DataFrame, row_index: int
):
    """Возвращает структуру данных для отчёта по сотруднику."""

    columns = list(data.columns)

    def find_column_index(name: str) -> int:
        """Find column index by name."""
        for i, col in enumerate(columns):
            if isinstance(col, str) and col.strip() == name:
                return i
        return -1

    def get_value_by_offset(base_col: str, offset: int = 0, currency: bool = False, unit: str = "", round_value: bool = True):
        """
        Get value from column with offset.
        For merged Excel headers, the actual value might be in offset column.
        offset=0 means the named column itself.
        """
        idx = find_column_index(base_col)
        if idx < 0:
            return "Нет данных"

        # Try the offset column first, then fall back to base column
        target_idx = idx + offset
        if target_idx >= len(columns):
            target_idx = idx

        try:
            value = data.iat[row_index, target_idx]
            if pd.isna(value):
                # Try base column if offset gave NaN
                if offset != 0:
                    value = data.iat[row_index, idx]
                    if pd.isna(value):
                        return "Нет данных"
                else:
                    return "Нет данных"
            if isinstance(value, str):
                if "error" in value.lower():
                    return "Ошибка данных"
                # Try to extract number from string like "1 365 ₽"
                clean = value.replace(" ", "").replace("₽", "").replace("Р", "").replace("-", "").strip()
                if not clean:
                    return "0 ₽" if currency else "0"
                try:
                    value = float(clean)
                except ValueError:
                    return value
            value = float(value)
            if round_value:
                value = int(round(value))
            if currency:
                return f"{value} ₽"
            if unit:
                return f"{value} {unit}"
            return str(value)
        except Exception as e:
            log(f"Error reading {base_col}+{offset}: {e}")
            return "Нет данных"

    def get_value(column: str, currency: bool = False, unit: str = "", round_value: bool = True):
        """Get value - tries offset 0 first, then offset 1-3 for merged cells."""
        # First try direct column
        result = get_value_by_offset(column, 0, currency, unit, round_value)
        if result not in ("Нет данных", "0 ₽", "0"):
            return result

        # Try offsets 1-3 for merged cell structures (4 columns per category)
        for offset in [1, 2, 3]:
            result = get_value_by_offset(column, offset, currency, unit, round_value)
            if result not in ("Нет данных", "0 ₽", "0"):
                return result

        # Return whatever we got from offset 0
        return get_value_by_offset(column, 0, currency, unit, round_value)

    def format_kpi(value, num1, text1, num2, text2):
        try:
            # Handle string values like "1%"
            if isinstance(value, str):
                clean = value.replace("%", "").replace(",", ".").strip()
                if not clean:
                    return "не начисляется"
                value = float(clean) / 100 if float(clean) > 1 else float(clean)
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
