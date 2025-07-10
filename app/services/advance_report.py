from datetime import datetime
from typing import Iterable, Optional

import pandas as pd


from .advance_requests import load_advance_requests


def dataframe_to_markdown(df: pd.DataFrame) -> str:
    """Преобразует DataFrame в выровненную Markdown-таблицу.

    Все столбцы имеют одинаковую ширину, достаточную для размещения
    самого длинного значения. Это упрощает чтение отчёта в текстовом виде.
    """
    if df.empty:
        return ""

    headers = list(df.columns)
    str_df = df.astype(str)

    # Определяем максимальную ширину среди всех ячеек и заголовков
    width = max(
        max(len(h) for h in headers),
        max(len(val) for val in str_df.to_numpy().ravel()),
    )

    def pad(text: str) -> str:
        return text.ljust(width)

    lines = []
    lines.append("| " + " | ".join(pad(h) for h in headers) + " |")
    lines.append("|" + "|".join(["-" * width] * len(headers)) + "|")
    for _, row in str_df.iterrows():
        lines.append(
            "| " + " | ".join(pad(val) for val in row.tolist()) + " |"
        )

    return "\n".join(lines)


def save_markdown_file(
        df: pd.DataFrame,
        filename: str = "advance_report.md") -> str:
    """Сохраняет DataFrame в Markdown-файл и возвращает имя файла."""
    data = dataframe_to_markdown(df)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(data)
    return filename


def generate_advance_report(
    start_date: datetime.date,
    end_date: datetime.date,
    statuses: Optional[Iterable[str]] = None,
) -> pd.DataFrame:
    """Возвращает DataFrame с запросами аванса за указанный период и статусы."""
    requests = load_advance_requests()
    rows = []
    for req in requests:
        if req.get("payout_type") != "Аванс":
            continue
        ts = req.get("timestamp")
        if not ts:
            continue
        try:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").date()
        except Exception:
            continue
        if start_date <= dt <= end_date:
            if statuses and req.get("status") not in statuses:
                continue
            rows.append(
                {
                    "Дата": dt.strftime("%Y-%m-%d"),
                    "Сотрудник": req.get("name", "—"),
                    "Сумма": req.get("amount", 0),
                    "Метод": req.get("method", "—"),
                    "Статус": req.get("status", "—"),
                }
            )
    df = pd.DataFrame(
        rows, columns=["Дата", "Сотрудник", "Сумма", "Метод", "Статус"]
    )
    if not df.empty:
        df.sort_values(by=["Сотрудник", "Дата"], inplace=True)
    return df
