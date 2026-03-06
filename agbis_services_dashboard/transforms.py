from __future__ import annotations

import re
import pandas as pd


GROUP_RULES = [
    ("Набойки", r"^1\."),          # 1.xx
    ("Свободная услуга", r"^10\."),# 10.xx
    ("Срочность", r"^144\."),      # 144.xx
    ("Профилактика", r"^2\."),     # 2.xx
    ("Химчистка", r"^20\d\."),    # 20x.x (пример: 201.1)
    ("Каблуки", r"^3\."),          # 3.xx
    ("Задник/стельки/подносок", r"^4\."), # 4.xx
    ("Подошва", r"^5\."),          # 5.xx
    ("Молния", r"^6\."),           # 6.xx
    ("Ушивка/ремни", r"^7\."),     # 7.xx
    ("Растяжка", r"^8\."),         # 8.xx
]


def add_service_group(df: pd.DataFrame) -> pd.DataFrame:
    if "code" not in df.columns:
        df["service_group"] = "Неизвестно"
        return df

    code = df["code"].fillna("").astype(str)
    group = pd.Series(["Другое"] * len(df), index=df.index)

    for label, pattern in GROUP_RULES:
        mask = code.str.contains(pattern, regex=True, na=False)
        group = group.where(~mask, other=label)

    df = df.copy()
    df["service_group"] = group
    return df


def apply_text_filter(series: pd.Series, text: str) -> pd.Series:
    """Case-insensitive contains. Пустая строка -> всё True."""
    if not text:
        return pd.Series([True] * len(series), index=series.index)
    s = series.fillna("").astype(str)
    return s.str.contains(re.escape(text), case=False, na=False)
