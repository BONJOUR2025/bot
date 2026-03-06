"""Service for fetching and aggregating master works data from Firebird."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

import pandas as pd

try:
    import fdb
    FIREBIRD_AVAILABLE = True
except ImportError:
    fdb = None
    FIREBIRD_AVAILABLE = False

from app.settings import settings

BASE_SQL = """
select
    docs.doc_date,
    docs.doc_num,
    doc_order_services.barcode_read,
    doc_order_services.id,
    tovars_tbl.code,
    tovars_tbl.name,
    doc_order_services.kredit,
    user_session_actions.date_beg,
    user_session_actions.date_end,
    user_session_actions.work_place_id,
    user_session_actions.barcode,
    users.description,
    docs_order.status_id

from doc_order_services

inner join docs_order
    on doc_order_services.doc_order_id = docs_order.id

inner join docs
    on docs_order.doc_id = docs.doc_id

inner join tovars_tbl
    on doc_order_services.tovar_id = tovars_tbl.tovar_id

inner join user_session_actions
    on doc_order_services.id = user_session_actions.doc_order_services_id

inner join user_session
    on user_session_actions.user_session_id = user_session.id

left join users
    on user_session.user_id = users.user_id

where
      user_session_actions.work_place_id in
      (1107,11017,11019,1108,11018,11020,11022,11024,1154,11028)
  and
      tovars_tbl.folder_id in
      (327,210289,416,210282,216,210347,210307,210320,210365,417,418,210348,210350,210349,210405,
       326,328,210290,210281,210268,210276,210267,215,210275,210269,210278,108401,329,330,108402,
       210270,210334,210337,210341,210336,210338,210340,210342,210343,210345,210346,210291,210292,
       210293,110409,210297,210298,210299,210283,210308,110410,110411,210309,210310,210314,210315,
       210316,210300,210306,210322,210323,210319,210318,210317,210326,210332,210333,210355,210358,
       210363,210357,210359,210361,210364,419,210280,210273,221,210272,217,210277,210366,210344,
       210356,210286,210274,210271,210335,210353,210279,210288,210380,210339,210399,210360,210384,
       210296,210266,210313,210331,210295,210287,210294,210285,210284,210325,210324,210330,210321,
       210329,210328,210327,210305,210312,210304,210311,210303,210302,210301,210351,210352,210382,
       210385,210377,210391,210394,210392,210378,210393,210388,210396,210395,210381,210390,210389,
       210397,210383,210386,210379,210387,110407,110421)
  AND DOC_DATE > '2023-01-01'
"""

WP_IN = {1107, 11017, 11019}
WP_OUT = {1108, 11018, 11020, 11022, 11024, 1154, 11028}

GROUP_RULES = [
    ("Набойки", r"^1\."),
    ("Свободная услуга", r"^10\."),
    ("Срочность", r"^144\."),
    ("Профилактика", r"^2\."),
    ("Химчистка", r"^20\d\."),
    ("Каблуки", r"^3\."),
    ("Задник/стельки/подносок", r"^4\."),
    ("Подошва", r"^5\."),
    ("Молния", r"^6\."),
    ("Ушивка/ремни", r"^7\."),
    ("Растяжка", r"^8\."),
]


def _add_service_group(df: pd.DataFrame) -> pd.DataFrame:
    if "code" not in df.columns:
        df["service_group"] = "Другое"
        return df
    code = df["code"].fillna("").astype(str)
    group = pd.Series(["Другое"] * len(df), index=df.index)
    for label, pattern in GROUP_RULES:
        mask = code.str.contains(pattern, regex=True, na=False)
        group = group.where(~mask, other=label)
    df = df.copy()
    df["service_group"] = group
    return df


def _normalize_wp(col: pd.Series) -> pd.Series:
    s = col.fillna("").astype(str).str.replace(r"[^\d]", "", regex=True)
    return pd.to_numeric(s, errors="coerce")


def _build_service_table(df_raw: pd.DataFrame) -> pd.DataFrame:
    if df_raw.empty:
        return pd.DataFrame()

    df = df_raw.copy()
    service_key = "barcode" if "barcode" in df.columns else "barcode_read"
    if service_key not in df.columns:
        return pd.DataFrame()

    df[service_key] = df[service_key].astype("string")
    df["work_place_id"] = _normalize_wp(df["work_place_id"])
    df["is_in"] = df["work_place_id"].isin(WP_IN)
    df["is_out"] = df["work_place_id"].isin(WP_OUT)

    in_time = df[df["is_in"]].groupby(service_key)["date_beg"].min()
    out_time = df[df["is_out"]].groupby(service_key)["date_beg"].min()

    g = df.groupby(service_key, dropna=False)

    def first_or_na(colname):
        return g[colname].first() if colname in df.columns else pd.NA

    service = pd.DataFrame({
        "service_id":    g[service_key].first(),
        "doc_num":       first_or_na("doc_num"),
        "description":   first_or_na("description"),
        "code":          first_or_na("code"),
        "name":          first_or_na("name"),
        "service_group": first_or_na("service_group"),
        "last_event":    g["date_beg"].max(),
        "HAS_IN":        g["is_in"].any(),
        "HAS_OUT":       g["is_out"].any(),
        "status_id":     first_or_na("status_id"),
    }).reset_index(drop=True)

    service["in_time"] = service["service_id"].map(in_time)
    service["out_time"] = service["service_id"].map(out_time)

    service["status"] = "Прочее"
    service.loc[service["HAS_IN"] & service["HAS_OUT"], "status"] = "Выполнено"
    service.loc[service["HAS_IN"] & ~service["HAS_OUT"], "status"] = "В работе"
    # Заказы с status_id = 5 не должны показываться как "В работе"
    closed = service["status_id"].astype("Int64", errors="ignore") == 5
    service.loc[closed & (service["status"] == "В работе"), "status"] = "Выполнено"

    service["duration_min"] = pd.NA
    done = service["status"] == "Выполнено"
    service.loc[done, "duration_min"] = (
        (service.loc[done, "out_time"] - service.loc[done, "in_time"])
        .dt.total_seconds() / 60.0
    )

    return service


def fetch_works(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[dict]:
    """Query Firebird and return aggregated service works as list of dicts."""
    if not FIREBIRD_AVAILABLE:
        return []

    sql = BASE_SQL
    params: list = []

    if date_from:
        sql += "\n  AND user_session_actions.date_beg >= CAST(? AS DATE)"
        params.append(str(date_from))

    if date_to:
        # date_to is inclusive — query up to next day midnight
        next_day = date_to + timedelta(days=1)
        sql += "\n  AND user_session_actions.date_beg <  CAST(? AS DATE)"
        params.append(str(next_day))

    con = fdb.connect(
        host=settings.firebird_host,
        port=settings.firebird_port,
        database=settings.firebird_database,
        user=settings.firebird_user,
        password=settings.firebird_password,
        charset=settings.firebird_charset,
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
    if df.empty:
        return []

    for col in ("doc_date", "date_beg", "date_end"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    for col in ("description", "doc_num", "code", "name"):
        if col in df.columns:
            df[col] = df[col].astype("string")

    df = _add_service_group(df)
    service_df = _build_service_table(df)

    if service_df.empty:
        return []

    # Convert timestamps to ISO strings for JSON
    for col in ("in_time", "out_time", "last_event"):
        if col in service_df.columns:
            service_df[col] = service_df[col].apply(
                lambda v: v.isoformat() if pd.notna(v) else None
            )

    service_df["duration_min"] = service_df["duration_min"].apply(
        lambda v: round(float(v), 1) if pd.notna(v) else None
    )

    result = service_df.drop(columns=["HAS_IN", "HAS_OUT", "status_id"], errors="ignore")

    # Replace all remaining NaN / pd.NA / inf with None so json.dumps won't fail
    import math

    def _safe(v):
        if v is None:
            return None
        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v

    return [
        {k: _safe(val) for k, val in row.items()}
        for row in result.to_dict(orient="records")
    ]
