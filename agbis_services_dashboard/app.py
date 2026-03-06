from __future__ import annotations

import re
import pandas as pd
import streamlit as st
import plotly.express as px

from db import load_config, fetch_services_df
from transforms import add_service_group, apply_text_filter

# =========================
# CONFIG / CONSTANTS
# =========================
st.set_page_config(page_title="Agbis • Услуги", layout="wide")
st.title("Agbis • Дашборд услуг")

# Этапы (как ты уточнил)
WP_IN = {1107, 11017, 11019}
WP_OUT = {1108, 11018, 11020, 11022, 11024, 1154, 11028}


# =========================
# UTILS
# =========================
def filter_code_list(series: pd.Series, raw: str) -> pd.Series:
    """
    Поддержка ввода списка кодов/префиксов через запятую/пробел/;.
    Примеры:
      "2.17, 2.18, 1.21"
      "2."  -> префикс (startswith)
    """
    if not raw:
        return pd.Series([True] * len(series), index=series.index)

    s = series.fillna("").astype(str)
    tokens = [t.strip() for t in re.split(r"[,\s;]+", raw) if t.strip()]
    if not tokens:
        return pd.Series([True] * len(series), index=series.index)

    mask = pd.Series(False, index=series.index)
    for t in tokens:
        if t.endswith("."):
            mask |= s.str.startswith(t, na=False)
        else:
            mask |= s.str.contains(t, case=False, regex=False, na=False)
    return mask


def normalize_work_place_id(col: pd.Series) -> pd.Series:
    """
    Приводим work_place_id к числу устойчиво к:
    - "1 107" (с пробелом)
    - "1 107" (с NBSP)
    - любым форматированным строкам
    """
    s = col.fillna("").astype(str)
    s = s.str.replace(r"[^\d]", "", regex=True)  # оставляем только цифры
    return pd.to_numeric(s, errors="coerce")


def build_service_table(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    1 строка = 1 услуга (по user_session_actions.barcode если есть, иначе barcode_read).
    Строим признаки:
      HAS_IN / HAS_OUT
      IN_TIME / OUT_TIME
      STATUS (Выполнено / В работе / Прочее)
      DURATION_MIN (для выполненных)
      last_event_time (для сортировки списка)
    """
    need = {"work_place_id", "date_beg"}
    missing = need - set(df_raw.columns)
    if missing:
        raise ValueError(f"В данных нет обязательных колонок: {missing}")

    df = df_raw.copy()

    # Определяем ключ услуги: barcode (уникальный) предпочтительнее barcode_read
    service_key = "barcode" if "barcode" in df.columns else "barcode_read"
    if service_key not in df.columns:
        raise ValueError("В данных нет ни barcode, ни barcode_read — невозможно агрегировать услуги.")

    # Приводим ключи
    df[service_key] = df[service_key].astype("string")
    if "barcode_read" in df.columns:
        df["barcode_read"] = df["barcode_read"].astype("string")
    if "barcode" in df.columns:
        df["barcode"] = df["barcode"].astype("string")

    # NBSP-safe нормализация work_place_id
    df["work_place_id"] = normalize_work_place_id(df["work_place_id"])

    df["is_in"] = df["work_place_id"].isin(WP_IN)
    df["is_out"] = df["work_place_id"].isin(WP_OUT)

    # Быстро (без groupby.apply)
    in_time = (
        df[df["is_in"]]
        .groupby(service_key)["date_beg"]
        .min()
    )
    out_time = (
        df[df["is_out"]]
        .groupby(service_key)["date_beg"]
        .min()
    )

    g = df.groupby(service_key, dropna=False)

    def first_or_na(colname: str):
        return g[colname].first() if colname in df.columns else pd.NA

    service = pd.DataFrame({
        "SERVICE_ID": g[service_key].first(),            # ключ услуги
        "barcode": first_or_na("barcode"),
        "barcode_read": first_or_na("barcode_read"),

        "doc_num": first_or_na("doc_num"),
        "description": first_or_na("description"),
        "code": first_or_na("code"),
        "name": first_or_na("name"),
        "service_group": first_or_na("service_group"),

        "last_event_time": g["date_beg"].max(),
        "HAS_IN": g["is_in"].any(),
        "HAS_OUT": g["is_out"].any(),
    }).reset_index(drop=True)

    service["IN_TIME"] = service["SERVICE_ID"].map(in_time)
    service["OUT_TIME"] = service["SERVICE_ID"].map(out_time)

    service["STATUS"] = "Прочее"
    service.loc[service["HAS_IN"] & service["HAS_OUT"], "STATUS"] = "Выполнено"
    service.loc[service["HAS_IN"] & ~service["HAS_OUT"], "STATUS"] = "В работе"

    # last_event_time гарантированно
    service["last_event_time"] = service["last_event_time"].fillna(service["OUT_TIME"]).fillna(service["IN_TIME"])

    # duration
    service["DURATION_MIN"] = pd.NA
    done = service["STATUS"] == "Выполнено"
    service.loc[done, "DURATION_MIN"] = (
        (service.loc[done, "OUT_TIME"] - service.loc[done, "IN_TIME"]).dt.total_seconds() / 60.0
    )

    return service


@st.cache_data(ttl=300, show_spinner=True)
def load_data_cached(date_from_str: str | None, date_to_str: str | None) -> pd.DataFrame:
    cfg = load_config()
    df_ = fetch_services_df(cfg, date_from=date_from_str, date_to=date_to_str)
    df_ = add_service_group(df_)
    return df_


# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.header("Фильтры")

    date_from = st.date_input("Дата от (DATE_BEG)", value=pd.to_datetime("2024-01-01").date())
    date_to = st.date_input("Дата до (DATE_BEG)", value=pd.Timestamp.today().date())
    date_to_plus1 = (pd.to_datetime(date_to) + pd.Timedelta(days=1)).date()

    use_sql_date_filter = st.checkbox("Фильтровать период сразу в SQL", value=True)

    st.divider()
    status_filter = st.radio("Статус", ["Все", "Выполнено", "В работе"], index=0)

    exec_search = st.text_input("Исполнитель содержит", value="")
    name_search = st.text_input("Название услуги содержит", value="")
    doc_search = st.text_input("Заказ содержит", value="")
    code_search = st.text_input("CODE (можно список)", value="", placeholder="2.17, 2.18, 1.21 или 2.")

    st.divider()
    st.subheader("Отображение")
    show_all_rows = st.checkbox("Показывать ВСЕ строки (может тормозить)", value=False)
    rows_limit = st.slider("Лимит строк", 100, 50000, 5000, step=100)
    top_n = st.slider("TOP N исполнителей", 5, 100, 20)

    st.divider()
    st.subheader("Графики")
    chosen_master = st.selectbox("Мастер (для графиков)", options=["(все)"], index=0)

    st.divider()
    debug_wp = st.checkbox("DEBUG: показать распределение work_place_id", value=False)


# =========================
# LOAD RAW EVENTS
# =========================
if use_sql_date_filter:
    df_raw = load_data_cached(str(date_from), str(date_to_plus1))
else:
    df_raw = load_data_cached(None, None)
    if "date_beg" in df_raw.columns:
        df_raw = df_raw[(df_raw["date_beg"] >= pd.to_datetime(date_from)) & (df_raw["date_beg"] < pd.to_datetime(date_to_plus1))]

# DEBUG: проверка work_place_id
if debug_wp and "work_place_id" in df_raw.columns:
    st.subheader("DEBUG: work_place_id (как пришло из БД)")
    st.write("sample raw:", df_raw["work_place_id"].dropna().astype(str).head(30).tolist())
    wp_norm = normalize_work_place_id(df_raw["work_place_id"])
    st.write("unique normalized (top 50):", sorted([int(x) for x in wp_norm.dropna().unique().tolist()])[:50])

# Текстовые фильтры по событиям
if exec_search and "description" in df_raw.columns:
    df_raw = df_raw[apply_text_filter(df_raw["description"], exec_search)]
if name_search and "name" in df_raw.columns:
    df_raw = df_raw[apply_text_filter(df_raw["name"], name_search)]
if doc_search and "doc_num" in df_raw.columns:
    df_raw = df_raw[apply_text_filter(df_raw["doc_num"], doc_search)]
if code_search and "code" in df_raw.columns:
    df_raw = df_raw[filter_code_list(df_raw["code"], code_search)]

# =========================
# BUILD 1 ROW PER SERVICE
# =========================
df = build_service_table(df_raw)

# Статус фильтр
if status_filter == "Выполнено":
    df = df[df["STATUS"] == "Выполнено"]
elif status_filter == "В работе":
    df = df[df["STATUS"] == "В работе"]

# Мультиселекты по мастерам/группам уже на уровне услуг
colA, colB = st.columns(2)
with colA:
    masters = sorted(df["description"].fillna("—").unique().tolist()) if "description" in df.columns else []
    master_sel = st.multiselect("Исполнитель", options=masters, default=masters)
with colB:
    groups = sorted(df["service_group"].fillna("—").unique().tolist()) if "service_group" in df.columns else []
    group_sel = st.multiselect("Группа услуг", options=groups, default=groups)

if master_sel and "description" in df.columns:
    df = df[df["description"].fillna("—").isin(master_sel)]
if group_sel and "service_group" in df.columns:
    df = df[df["service_group"].fillna("—").isin(group_sel)]

# Обновим список мастеров для графиков
if "description" in df.columns and not df.empty:
    master_list_for_charts = ["(все)"] + sorted(df["description"].fillna("—").unique().tolist())
else:
    master_list_for_charts = ["(все)"]
if chosen_master not in master_list_for_charts:
    chosen_master = "(все)"


# =========================
# KPI
# =========================
st.divider()
k1, k2, k3, k4 = st.columns(4)
k1.metric("Услуг (1 строка = 1 услуга)", f"{len(df):,}".replace(",", " "))
k2.metric("Выполнено", f"{(df['STATUS']=='Выполнено').sum():,}".replace(",", " "))
k3.metric("В работе", f"{(df['STATUS']=='В работе').sum():,}".replace(",", " "))
k4.metric("Мастеров", f"{df['description'].nunique(dropna=True):,}".replace(",", " ") if "description" in df.columns else "—")


# =========================
# TABS: ANALYTICS
# =========================
st.divider()
tab1, tab2, tab3, tab4 = st.tabs(
    ["Загрузка по дням", "Время выполнения", "Скорость мастеров", "Очередь работ"]
)

with tab1:
    st.subheader("Загрузка по дням (выполненные)")
    done = df[df["STATUS"] == "Выполнено"].copy()
    if done.empty:
        st.info("Нет выполненных услуг по текущим фильтрам.")
    else:
        done["done_day"] = done["OUT_TIME"].dt.date
        if chosen_master != "(все)" and "description" in done.columns:
            done = done[done["description"].fillna("—") == chosen_master]
        daily = done.groupby("done_day").size().reset_index(name="services_done").sort_values("done_day")
        st.dataframe(daily, use_container_width=True, hide_index=True)
        st.plotly_chart(px.line(daily, x="done_day", y="services_done"), use_container_width=True)

with tab2:
    st.subheader("Время выполнения (только выполненные)")
    done = df[df["STATUS"] == "Выполнено"].copy()
    done = done[done["DURATION_MIN"].notna()]
    if done.empty:
        st.info("Нет данных по длительности.")
    else:
        done = done[(done["DURATION_MIN"] >= 0) & (done["DURATION_MIN"] <= 60 * 24 * 30)]
        if done.empty:
            st.info("После отсечки аномалий данных не осталось.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Среднее", f"{float(done['DURATION_MIN'].mean()):.1f} мин")
            c2.metric("Медиана", f"{float(done['DURATION_MIN'].median()):.1f} мин")
            c3.metric("90-й перцентиль", f"{float(done['DURATION_MIN'].quantile(0.90)):.1f} мин")
            st.plotly_chart(px.histogram(done, x="DURATION_MIN", nbins=40), use_container_width=True)

with tab3:
    st.subheader("Скорость мастеров (медиана времени)")
    done = df[df["STATUS"] == "Выполнено"].copy()
    done = done[done["DURATION_MIN"].notna()]
    if done.empty or "description" not in done.columns:
        st.info("Нет данных для рейтинга скорости.")
    else:
        done = done[(done["DURATION_MIN"] >= 0) & (done["DURATION_MIN"] <= 60 * 24 * 30)]
        min_jobs = st.slider("Мин. выполненных услуг для рейтинга", 1, 50, 5)

        speed = (
            done.groupby("description")
            .agg(
                services_done=("SERVICE_ID", "count"),
                median_min=("DURATION_MIN", "median"),
                avg_min=("DURATION_MIN", "mean"),
                p90_min=("DURATION_MIN", lambda s: float(s.quantile(0.90))),
            )
            .reset_index()
        )
        speed = speed[speed["services_done"] >= min_jobs]
        speed = speed.sort_values(["median_min", "services_done"], ascending=[True, False])

        st.dataframe(speed, use_container_width=True, hide_index=True)
        st.plotly_chart(px.bar(speed.head(30), x="description", y="median_min"), use_container_width=True)

with tab4:
    st.subheader("Очередь работ (услуги в работе)")
    wip = df[df["STATUS"] == "В работе"].copy()
    if wip.empty:
        st.success("Очередь пуста: по текущим фильтрам нет услуг «в работе».")
    else:
        now = pd.Timestamp.now()
        wip["AGE_HOURS"] = ((now - wip["IN_TIME"]).dt.total_seconds() / 3600.0).round(2)

        c1, c2, c3 = st.columns(3)
        c1.metric("В работе сейчас", f"{len(wip):,}".replace(",", " "))
        c2.metric("Средний возраст (ч)", f"{float(wip['AGE_HOURS'].mean()):.1f}")
        c3.metric("Медианный возраст (ч)", f"{float(wip['AGE_HOURS'].median()):.1f}")

        cols = [c for c in ["AGE_HOURS", "IN_TIME", "doc_num", "description", "code", "name", "service_group", "barcode", "barcode_read", "SERVICE_ID"] if c in wip.columns]
        st.dataframe(wip.sort_values("AGE_HOURS", ascending=False)[cols].head(300), use_container_width=True)

        if "description" in wip.columns:
            by_master = wip.groupby("description").size().reset_index(name="in_work_cnt").sort_values("in_work_cnt", ascending=False)
            st.subheader("Очередь по мастерам")
            st.dataframe(by_master, use_container_width=True, hide_index=True)
            st.plotly_chart(px.bar(by_master.head(30), x="description", y="in_work_cnt"), use_container_width=True)


# =========================
# SUMMARIES + MATRIX + FULL LIST
# =========================
st.divider()

st.subheader("Сводка по исполнителям (все статусы)")
if "description" in df.columns and not df.empty:
    agg_exec = (
        df.groupby("description")
        .size()
        .reset_index(name="services_cnt")
        .sort_values("services_cnt", ascending=False)
        .head(top_n)
    )
    st.dataframe(agg_exec, use_container_width=True, hide_index=True)
    st.plotly_chart(px.bar(agg_exec, x="description", y="services_cnt"), use_container_width=True)
else:
    st.info("Нет данных по исполнителям для текущих фильтров.")

st.subheader("Матрица: исполнитель × группа (все статусы)")
if {"description", "service_group"}.issubset(df.columns) and not df.empty:
    pivot = pd.pivot_table(
        df,
        index="description",
        columns="service_group",
        values="SERVICE_ID",
        aggfunc="count",
        fill_value=0,
    )
    pivot["Итого"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("Итого", ascending=False)
    st.dataframe(pivot, use_container_width=True)
else:
    st.info("Для матрицы нужны поля description и service_group, и ненулевая выборка.")

st.subheader("Полный список услуг по фильтру (1 строка = 1 услуга)")

cols = [c for c in [
    "last_event_time",
    "STATUS", "HAS_IN", "HAS_OUT",
    "IN_TIME", "OUT_TIME", "DURATION_MIN",
    "doc_num", "description", "code", "name",
    "service_group",
    "barcode", "barcode_read", "SERVICE_ID",
] if c in df.columns]

df_view = df[cols].copy() if cols else df.copy()

# безопасная сортировка
if "last_event_time" in df_view.columns:
    df_view = df_view.sort_values("last_event_time", ascending=False)
elif "OUT_TIME" in df_view.columns:
    df_view = df_view.sort_values("OUT_TIME", ascending=False)
elif "IN_TIME" in df_view.columns:
    df_view = df_view.sort_values("IN_TIME", ascending=False)

if (not show_all_rows) and (len(df_view) > rows_limit):
    st.warning(f"Показаны первые {rows_limit:,} строк из {len(df_view):,}.".replace(",", " "))
    df_view = df_view.head(rows_limit)

st.dataframe(df_view, use_container_width=True)

st.download_button(
    "Скачать текущую выборку в CSV",
    data=df.to_csv(index=False).encode("utf-8-sig"),
    file_name="agbis_services_1row_per_service.csv",
    mime="text/csv",
)