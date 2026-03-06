from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import pandas as pd
from dotenv import load_dotenv

from query import BASE_SQL


@dataclass
class FbConfig:
    host: str
    port: int
    db_path: str
    user: str
    password: str
    charset: str = "UTF8"


def load_config() -> FbConfig:
    load_dotenv()

    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "3050"))
    db_path = os.getenv("DB_PATH", r"C:\Agbis\DB\ARM_13.fdb")
    user = os.getenv("DB_USER", "SYSDBA")
    password = os.getenv("DB_PASSWORD", "masterkey")
    charset = os.getenv("DB_CHARSET", "UTF8")

    return FbConfig(
        host=host,
        port=port,
        db_path=db_path,
        user=user,
        password=password,
        charset=charset,
    )


def fetch_services_df(
    cfg: FbConfig,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> pd.DataFrame:
    """
    Firebird 2.5: используем драйвер fdb.
    date_from/date_to: строки 'YYYY-MM-DD' для фильтра по user_session_actions.date_beg.
    date_to рекомендуется передавать как "следующий день" (эксклюзивно), как у нас в app.py.
    """
    import fdb  # важно: импорт внутри функции, чтобы app.py грузился даже без драйвера

    sql = BASE_SQL
    params = []

    # ВАЖНО: в fdb позиционные параметры: "?" (не :name)
    if date_from:
        sql += "\n  AND user_session_actions.date_beg >= CAST(? AS DATE)"
        params.append(date_from)

    if date_to:
        sql += "\n  AND user_session_actions.date_beg <  CAST(? AS DATE)"
        params.append(date_to)

    con = fdb.connect(
        host=cfg.host,
        port=cfg.port,
        database=cfg.db_path,
        user=cfg.user,
        password=cfg.password,
        charset=cfg.charset,
    )

    try:
        cur = con.cursor()
        cur.execute(sql, params)

        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        try:
            con.close()
        except Exception:
            pass

    df = pd.DataFrame(rows, columns=cols)

    # даты
    for col in ("doc_date", "date_beg", "date_end"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # строки
    for col in ("description", "doc_num", "code", "name"):
        if col in df.columns:
            df[col] = df[col].astype("string")

    return df