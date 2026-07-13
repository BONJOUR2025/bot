"""Agbis LOCAL_OPTIONS / LOCAL_OPTION_VALUES for the "Настройки Agbis" admin page.

Agbis stores ~665 per-computer settings (LOCAL_OPTIONS = catalog with
description + default; LOCAL_OPTION_VALUES = per-LOCAL_COMPUTER_ID
override) under its own GROUP_OPTION_NAME, which is fine for hardware/
payment-terminal integrations (one vendor = one group) but leaves about a
third of the options — exactly the day-to-day workflow toggles like order
issuance, printing, warehouse transfers — dumped in a single ungrouped
bucket. `_classify` re-buckets everything into a smaller set of categories
a non-Agbis-admin can actually scan (see CATEGORY_ORDER), first by the
existing GROUP_OPTION_NAME where that's already a sensible unit, then by
OPTION_NAME/SHORT_DESCR keyword for the ungrouped remainder.
"""
from __future__ import annotations

import logging
import re

from app.services.firebird_service import FIREBIRD_AVAILABLE, _connect

logger = logging.getLogger(__name__)

_DB_NAME_RE = re.compile(r"ARM_(\w+?)\.fdb$", re.IGNORECASE)


def _decode(v):
    """A handful of these columns are BLOB SUB_TYPE TEXT (LOCAL_COMPUTERS_LIST.NAME,
    some VALUE_STR/DEFAULT_STR rows) that fdb hands back as raw `bytes` instead of
    `str` even with charset=UTF8 on the connection — the blob's own declared
    charset wins over the connection charset for those. The bytes are legacy
    Windows-1251 (same as the rest of this Delphi app's data), and passing raw
    bytes into FastAPI's jsonable_encoder crashes with UnicodeDecodeError since
    it assumes UTF-8.
    """
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8")
        except UnicodeDecodeError:
            return v.decode("cp1251", errors="replace")
    return v

_FISCAL_BANK_GROUPS = {
    "AlphaBank", "Arcus", "Bankomsvyaz", "CashaLotFR", "CheckBoxFR", "Chek",
    "Chon", "DatecsFP", "EHDM", "FiskAtol", "FiskFR", "FiskFR2", "FiskFR_kz",
    "HDMPrintFP", "Inpas", "MtbBank", "PosApi", "POSConnector", "Sberbank",
    "SwithBit", "Cipher", "Cipher2",
}
_HARDWARE_GROUPS = {
    "BarCode", "Barcode", "CasVes", "Conveyor", "RFID", "VFD", "VesReader",
    "Magn", "NFCReaders", "Anviz", "Microphone", "VESREADERLP15",
}
_COMMS_GROUPS = {"SMS", "SMTP", "IMAP", "INTERNET", "FreeSwitch"}
_EXTRA_MODULE_GROUPS = {"Hotel", "JTRIPS", "UDS"}

CATEGORY_ORDER = [
    "Заказы",
    "Накладные в пути (логистика между складами)",
    "Склады и кассы",
    "Печать чеков и бирок",
    "Электронная очередь",
    "Ограниченный режим рабочего места",
    "Прачечная и доп. модули",
    "Рабочие места (1-6)",
    "Мобильное приложение (АРМ)",
    "Оборудование (сканеры/весы/фото/прочее)",
    "Фискализация и эквайринг",
    "Связь и уведомления",
    "Отладка и логирование",
    "Прочие настройки",
]

_DEBUG_OPTION_NAMES = {
    "LogHttp", "BIG_LOG", "MEMORY_LOG", "WRITE_THREAD_LOG", "DEBUG",
    "DoSqlLog", "BedLog", "HangupMonActive",
}
_EQ_OPTION_NAMES = {"OPERATOR", "HALLID", "AutoDelEQ", "DelCountEQ", "EnableEQ"}
_CAMERA_TABLET_NAMES_SUBSTR = ("Camera", "Photo", "Tablet", "AgbisBarcodeScanner", "AgbisSign")

# Ground truth, not a guess: every option on Agbis's own "Настройки модуля →
# Основные → Заказы" screen (user-provided screenshot of the real desktop
# app), regardless of what GROUP_OPTION_NAME/keyword matching would
# otherwise infer. Two of these (Overhead, CreateAutoDocInWayAnScladTo) were
# previously misclassified into "Накладные в пути" / "Склады и кассы" by
# the keyword rules below — Agbis itself puts them under Заказы because
# they're triggered from the order-save flow, not the накладная screen.
_ORDERS_TAB_OPTIONS = {
    "UseOwnerOrder", "AllowNotFullPay", "AlwaysAskWhoOut", "OnlyReestr",
    "AllowChangeKassaSclad", "UseLastSclad", "UseLastDateOut",
    "AllowChangeOrderDate", "CorrectDiscountInOrder", "AllowChangeSclad",
    "AllowChangeKassa", "DontControlStatusOut", "DefOrderScladNum", "ZakazWP",
    "AllowChangePriceList", "AnyBSO", "OrderServsFontSize",
    "DontShowZakazItogs", "DontShowOtherPP", "NotPrintLabelAutomatically",
    "EditingDefaultBarCode", "SaleGoods", "ClearFilterLocalSclad",
    "Overhead", "CreateAutoDocInWayAnScladTo",
    "AwayOrders", "ForbidHimOrders", "OrderConfirmUse",
}


def _classify(group: str | None, option_name: str, short_descr: str) -> str:
    g = (group or "").strip()
    name = option_name or ""
    descr = (short_descr or "").lower()

    if name in _ORDERS_TAB_OPTIONS:
        return "Заказы"
    if g == "ARMHim":
        return "Мобильное приложение (АРМ)"
    if g == "WorkPlaces":
        return "Рабочие места (1-6)"
    if g in _FISCAL_BANK_GROUPS:
        return "Фискализация и эквайринг"
    if g in _HARDWARE_GROUPS:
        return "Оборудование (сканеры/весы/фото/прочее)"
    if g in _COMMS_GROUPS:
        return "Связь и уведомления"
    if g in _EXTRA_MODULE_GROUPS:
        return "Прачечная и доп. модули"
    if g in ("PrintBar", "PrintCheck", "OrderPrint"):
        return "Печать чеков и бирок"
    if g == "Additional":
        return "Ограниченный режим рабочего места"

    # Everything below has no GROUP_OPTION_NAME in Agbis (~1/3 of all
    # options) — split by keyword instead of one "прочее" bucket.
    if name in _EQ_OPTION_NAMES:
        return "Электронная очередь"
    if name in _DEBUG_OPTION_NAMES:
        return "Отладка и логирование"
    if name.startswith(("DocInWay", "InWay")):
        return "Накладные в пути (логистика между складами)"
    if "Out" in name or "выдач" in descr or "выдав" in descr:
        return "Заказы"
    if name.startswith("Print_") or "печат" in descr or "чек" in descr:
        return "Печать чеков и бирок"
    if "Laundry" in name or "Aeroflot" in name:
        return "Прачечная и доп. модули"
    if any(k in name for k in ("Sclad", "Kassa")):
        return "Склады и кассы"
    if "Zakaz" in name or "заказ" in descr:
        return "Заказы"
    if any(k in name for k in _CAMERA_TABLET_NAMES_SUBSTR):
        return "Оборудование (сканеры/весы/фото/прочее)"
    return "Прочие настройки"


def _effective_value(value_bool, value_int, value_str, value_flt,
                      default_bool, default_int, default_str, default_float):
    """Resolve the value actually in effect + whether it's an override.

    Firebird has no notion of "which typed column is the real one" for a
    row — Agbis's VALUE_TYPE marks that, but in practice each option only
    ever populates one of VALUE_BOOL/INT/STR/FLT, so first-non-null wins.
    """
    if value_bool is not None:
        return bool(value_bool), "override"
    if value_int is not None:
        return value_int, "override"
    if value_str is not None and value_str != "":
        return value_str, "override"
    if value_flt is not None:
        return value_flt, "override"
    if default_bool is not None:
        return bool(default_bool), "default"
    if default_int is not None:
        return default_int, "default"
    if default_str is not None and default_str != "":
        return default_str, "default"
    if default_float is not None:
        return default_float, "default"
    return None, "none"


def _best_description(option_name: str, short_descr: str | None, long_descr: str | None) -> str | None:
    """SHORT_DESCR is usually the better (shorter) human text, but about a
    tenth of Agbis's options leave it blank or equal to OPTION_NAME while
    LONG_DESCR actually has real Russian text (e.g. ConvARMBAM) — fall back
    to it. If both are blank/equal to the option name, there's genuinely no
    human description anywhere in the DB for that option.
    """
    for candidate in (short_descr, long_descr):
        c = (candidate or "").strip()
        if c and c != option_name:
            return c
    return None


def _computer_dep_number(db_name: str | None, dep_id_col: int | None) -> int | None:
    """The department a computer belongs to. LOCAL_COMPUTERS_LIST.DEP_ID
    itself is unreliable for computers whose DB_NAME already encodes the
    number (our own ARM_21 row has DEP_ID=0, clearly stale) — DB_NAME wins
    whenever it parses as a number. DEP_ID is only trusted as a fallback for
    the handful of departments named non-numerically in DB_NAME (ARM_Akad,
    ARM_ozerki, ARM_NEW), where it checks out against DEPS.
    """
    m = _DB_NAME_RE.search(db_name or "")
    suffix = m.group(1) if m else None
    if suffix and suffix.isdigit():
        return int(suffix)
    return dep_id_col or None


def _computer_label(db_name: str | None, dep_number: int | None, dep_names: dict[int, str]) -> str:
    if dep_number is not None and dep_number in dep_names:
        return dep_names[dep_number]
    m = _DB_NAME_RE.search(db_name or "")
    suffix = m.group(1) if m else None
    return suffix or db_name or "?"


def get_agbis_settings_matrix() -> dict:
    """Every LOCAL_OPTION, grouped into CATEGORY_ORDER buckets, with the
    effective value for every registered Agbis POS computer (Him.exe
    installs only — Updater.exe/AgbisAgentTasks.exe/AgbisAgentGUI.exe rows
    share the same computer physically but aren't a "settings screen").
    """
    empty = {"computers": [], "categories": []}
    if not FIREBIRD_AVAILABLE:
        return empty

    try:
        con = _connect()
        try:
            cur = con.cursor()

            cur.execute("""
                SELECT ID, NAME, IP, DEP_ID, DB_NAME
                FROM LOCAL_COMPUTERS_LIST
                WHERE PROJECT_NAME = 'Him.exe'
                ORDER BY DB_NAME
            """)
            computer_rows = cur.fetchall()
            computer_ids = [r[0] for r in computer_rows]

            cur.execute("SELECT DEP_ID, NAME FROM DEPS")
            dep_names = {dep_id: _decode(dep_name) for dep_id, dep_name in cur.fetchall()}

            cur.execute("""
                SELECT ID, GROUP_OPTION_NAME, OPTION_NAME, SHORT_DESCR, LONG_DESCR,
                       DEFAULT_BOOL, DEFAULT_INT, DEFAULT_STR, DEFAULT_FLOAT
                FROM LOCAL_OPTIONS
                ORDER BY GROUP_OPTION_NAME, ORDER_NUM, OPTION_NAME
            """)
            option_rows = cur.fetchall()

            values_by_key: dict[tuple[int, int], tuple] = {}
            if computer_ids:
                placeholders = ",".join("?" * len(computer_ids))
                cur.execute(f"""
                    SELECT LOCAL_OPTION_ID, LOCAL_COMPUTER_ID,
                           VALUE_BOOL, VALUE_INT, VALUE_STR, VALUE_FLT
                    FROM LOCAL_OPTION_VALUES
                    WHERE LOCAL_COMPUTER_ID IN ({placeholders})
                """, computer_ids)
                for opt_id, comp_id, v_bool, v_int, v_str, v_flt in cur.fetchall():
                    values_by_key[(opt_id, comp_id)] = (v_bool, v_int, v_str, v_flt)
        finally:
            con.close()
    except Exception as e:
        logger.error(f"get_agbis_settings_matrix error: {e}")
        return empty

    computers = []
    for comp_id, name, ip, dep_id, db_name in computer_rows:
        db_name = _decode(db_name)
        dep_number = _computer_dep_number(db_name, dep_id)
        hostname = _decode(name)
        computers.append({
            "id": comp_id,
            "label": _computer_label(db_name, dep_number, dep_names),
            "hostname": hostname.strip() if hostname else None,
            "ip": _decode(ip).strip() if ip else None,
            "db_name": db_name.strip() if db_name else None,
            "dep_id": dep_number,
        })
    computers.sort(key=lambda c: (c["label"] or "").lower())

    # Multiple physical terminals can share one department (e.g. two POS
    # registers at the same salon) — same label otherwise, so append the
    # hostname (falling back to IP) to just the colliding ones.
    label_counts: dict[str, int] = {}
    for c in computers:
        label_counts[c["label"]] = label_counts.get(c["label"], 0) + 1
    for c in computers:
        if label_counts.get(c["label"], 0) > 1:
            suffix = c["hostname"] or c["ip"]
            if suffix:
                c["label"] = f"{c['label']} · {suffix}"

    categories: dict[str, list[dict]] = {c: [] for c in CATEGORY_ORDER}
    for opt_id, group, option_name, short_descr, long_descr, d_bool, d_int, d_str, d_float in option_rows:
        group = _decode(group)
        option_name = _decode(option_name)
        short_descr = _decode(short_descr)
        long_descr = _decode(long_descr)
        d_str = _decode(d_str)
        descr = _best_description(option_name, short_descr, long_descr)
        cat = _classify(group, option_name, descr or "")
        values = {}
        for comp_id in computer_ids:
            v_bool, v_int, v_str, v_flt = values_by_key.get((opt_id, comp_id), (None, None, None, None))
            v_str = _decode(v_str)
            value, source = _effective_value(v_bool, v_int, v_str, v_flt, d_bool, d_int, d_str, d_float)
            values[str(comp_id)] = {"value": _decode(value), "source": source}
        categories.setdefault(cat, []).append({
            "id": opt_id,
            "option_name": option_name,
            "short_descr": descr,
            "group": group,
            "values": values,
        })

    return {
        "computers": computers,
        "categories": [
            {"name": name, "options": categories[name]}
            for name in CATEGORY_ORDER
            if categories.get(name)
        ],
    }
