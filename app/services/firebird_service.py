"""Firebird database connection service for sales data."""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from contextvars import ContextVar
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

try:
    import fdb
    FIREBIRD_AVAILABLE = True
except ImportError:
    fdb = None
    FIREBIRD_AVAILABLE = False

from app.settings import settings

logger = logging.getLogger(__name__)

# Set by run_with_timeout() before it dispatches a blocking call to a worker
# thread; _connect() fills in "attachment_id" as soon as it has one, so
# run_with_timeout can kill that specific attachment if the call overruns
# its deadline. asyncio.to_thread() copies the current context into the
# worker thread, so the ContextVar's value (the dict object itself, not a
# copy of its contents) is shared between both sides.
_attachment_holder_var: ContextVar[Optional[dict]] = ContextVar("_firebird_attachment_holder", default=None)


class TTLCache:
    """Thread-safe TTL cache with single-flight de-duplication for slow,
    thread-executed Firebird queries.

    The 2026-07-18 dashboard outage (see run_with_timeout / _kill_attachment)
    happened because every retry of a slow endpoint fired its own fresh
    Firebird query on top of the ones still running — the response time
    for these read-only reports/search queries is dominated by contention
    on the shared Agbis Firebird server (confirmed by timing the same
    query back-to-back: sub-second one run, 15-100s the next, with no
    code change), so piling on more concurrent identical queries only
    makes it worse. Caching the result for `ttl` seconds and making
    concurrent callers for the same key wait on one in-flight computation
    instead of starting their own turns a burst of identical
    dashboard/search requests into a single Firebird round trip.

    Expired entries are kept rather than dropped, so a caller whose fresh
    computation times out can still answer from the last good result via
    `get_stale` instead of failing outright — under the contention above, a
    report that was correct a few minutes ago beats a 504. `max_entries`
    bounds what that retention can cost: each entry here is a whole report,
    and the keys are user-chosen date ranges, so without a cap the map only
    ever grows.
    """

    def __init__(self, ttl: float, max_entries: int = 32):
        self._ttl = ttl
        self._max_entries = max_entries
        self._lock = threading.Lock()
        # key -> (expires_at, value, stored_at)
        self._entries: dict[Any, tuple[float, Any, float]] = {}
        self._inflight: dict[Any, threading.Lock] = {}

    def get_stale(self, key: Any) -> tuple[Any, float] | None:
        """Last value computed for `key` and its age in seconds, ignoring the
        TTL. None if nothing was ever computed for it."""
        with self._lock:
            entry = self._entries.get(key)
        if entry is None:
            return None
        return entry[1], time.monotonic() - entry[2]

    def _store(self, key: Any, value: Any) -> None:
        now = time.monotonic()
        self._entries[key] = (now + self._ttl, value, now)
        if len(self._entries) > self._max_entries:
            oldest = min(self._entries, key=lambda k: self._entries[k][2])
            self._entries.pop(oldest, None)

    def get_or_compute(self, key: Any, compute: Callable[[], Any]) -> Any:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry[0] > now:
                return entry[1]
            lock = self._inflight.get(key)
            owner = lock is None
            if owner:
                lock = threading.Lock()
                lock.acquire()
                self._inflight[key] = lock

        if not owner:
            with lock:
                pass
            with self._lock:
                entry = self._entries.get(key)
                fresh = entry is not None and entry[0] > time.monotonic()
            if fresh:
                return entry[1]
            # The owner we waited on finished without caching anything —
            # its compute() raised (see _search_clients_uncached /
            # _get_daily_sales_uncached). Re-enter get_or_compute() rather
            # than calling compute() directly: calling it directly here
            # means every one of N waiters fires its own Firebird query in
            # parallel the moment the owner fails — the exact pile-up this
            # cache exists to prevent, and it happens precisely when
            # Firebird is already struggling. Recursing lets one of the
            # waiters become the new owner and the rest queue behind it
            # again, same as on first entry.
            return self.get_or_compute(key, compute)

        try:
            result = compute()
            with self._lock:
                self._store(key, result)
            return result
        finally:
            lock.release()
            with self._lock:
                self._inflight.pop(key, None)


CODE_RE = re.compile(r"(\d{4})$")
ORDER_SALON_CODE_RE = re.compile(r"-(\d{1,2})$")


def _code_from_description(desc: str | None) -> str | None:
    """Extract 4-digit employee code from description like 'Имя 1234'."""
    desc = (desc or "").strip()
    m = CODE_RE.search(desc)
    return m.group(1) if m else None


def _order_salon_code(doc_num: str | None) -> str | None:
    """Extract the salon order-number suffix (e.g. '7' from '34247-7').

    Mirrors app.services.payroll_service._order_salon_code exactly — this
    is the same convention the existing payroll-by-salon report keys off,
    not DOCS.DEP_ID, so salon attribution here stays consistent with it.
    """
    m = ORDER_SALON_CODE_RE.search((doc_num or "").strip())
    return m.group(1) if m else None


_RECEIPT_DOC_NUM_RE = re.compile(r"Номер документа\s*:\s*(\S+?);?(?:\s|$)")
_WAREHOUSE_INVOICE_RE = re.compile(r"накладной\s+ВнНомер(\S+)")


def _humanize_order_action(
    basis: str,
    *,
    sclad_changed: bool = False,
    sclad_from: str | None = None,
    sclad_to: str | None = None,
) -> str:
    """Translate one Agbis DOCS_ORDER_HISTORY.BASIS string into a short
    plain-language summary for the "Пользователи АГБИС" action log — the
    raw text is kept alongside (see get_agbis_user_actions) so nothing is
    lost if this misses a pattern, it just falls back to the raw text.

    Every history row tied to a "накладная на перемещение" (BASIS starts
    with "Изменение текущего склада") gets the same templated BASIS text
    regardless of which step of the накладная it represents — Agbis writes
    one such row per user who touches it (create/dispatch, then separately
    accept), and only the row that actually flips CURRENT_SCLAD_ID is the
    real physical move; the others (typically the accepting side marking
    receipt, or a resave that doesn't progress the накладная) leave the
    field untouched. `sclad_changed` (computed by the caller by diffing
    CURRENT_SCLAD_ID against the previous history row for this order) is
    what disambiguates them — the raw BASIS text has no field for it, only
    the free-text "Дата приема: ..." substring hints at "accepted".
    """
    if basis.startswith('Сохранение заказа при создании'):
        return "Создали заказ"
    if basis.startswith('Распечатан чек'):
        m = _RECEIPT_DOC_NUM_RE.search(basis)
        return f"Распечатали чек полного расчёта (документ №{m.group(1)})" if m else "Распечатали чек полного расчёта"
    if basis.startswith('Выдача заказа'):
        return "Выдали заказ клиенту"
    if basis.startswith('Изменение текущего склада'):
        m = _WAREHOUSE_INVOICE_RE.search(basis)
        invoice = f" (накладная №{m.group(1)})" if m else ""
        if sclad_changed:
            return f"Переместили заказ со склада «{sclad_from}» на склад «{sclad_to}»{invoice}"
        if 'Дата приема' in basis:
            return f"Приняли накладную на перемещение{invoice}"
        return f"Пересохранили накладную на перемещение, склад не менялся{invoice}"
    if 'изменена сумма' in basis:
        return "Изменили сумму услуги"
    if basis.startswith('СМС сформированная для отправки'):
        return "Сформировали СМС клиенту"
    if basis.startswith('Новое изменение статуса СМС'):
        return "Обновился статус СМС"
    if basis.startswith('Сохранение заказа при изменении'):
        return "Изменили заказ"
    return basis or "Действие без описания"


class _SalonResolver:
    """Resolves (doc_num, doc_date) -> salon_id for a batch of rows.

    SalonRepository.get_by_order_code() re-reads salons.json from disk on
    every call (by design, for the two-process HR/payroll setup) — fine
    for occasional lookups, but for the thousands of order rows a
    salon-filtered report processes it dominates runtime (measured:
    ~4s/10k calls vs ~0.03s/10k with the reload suppressed). Use as:

        with _SalonResolver() as resolve:
            salon_id = resolve(doc_num, doc_date)
    """

    def __enter__(self):
        from app.data.salon_repository import get_salon_repository
        self._repo = get_salon_repository()
        self._repo._load()
        self._original_load = self._repo._load
        self._repo._load = lambda: None
        return self._resolve

    def _resolve(self, doc_num, doc_date) -> str | None:
        code = _order_salon_code(doc_num)
        if not code or doc_date is None:
            return None
        salon = self._repo.get_by_order_code(code, doc_date.year, doc_date.month)
        return salon.id if salon else None

    def __exit__(self, *exc_info):
        self._repo._load = self._original_load


def _month_range(year: int, month: int) -> tuple[date, date]:
    """Return (start, exclusive_end) dates for a month."""
    if month == 12:
        return date(year, 12, 1), date(year + 1, 1, 1)
    return date(year, month, 1), date(year, month + 1, 1)


def _connect():
    """Create Firebird connection using dsn format host/port:path."""
    con = fdb.connect(
        dsn=f"{settings.firebird_host}/{settings.firebird_port}:{settings.firebird_database}",
        user=settings.firebird_user or "SYSDBA",
        password=settings.firebird_password or "masterkey",
        charset=settings.firebird_charset,
    )
    holder = _attachment_holder_var.get()
    if holder is not None:
        try:
            cur = con.cursor()
            cur.execute("SELECT CURRENT_CONNECTION FROM RDB$DATABASE")
            holder["attachment_id"] = cur.fetchone()[0]
        except Exception:
            pass
    return con


def _kill_attachment(attachment_id: int) -> None:
    """Force-disconnect a stuck Firebird attachment.

    Python threads can't be cancelled, so a blocking call left running past
    run_with_timeout()'s deadline just keeps executing (and holding its
    Firebird transaction/connection open) forever — every retry piles
    another leaked attachment on top of the last, degrading the whole
    server (this is what caused the 2026-07-18 dashboard outage: 10 stuck
    attachments accumulated in ~4 minutes from repeated /masters/works
    retries). Disconnecting the attachment from here makes Firebird raise
    inside the stuck thread's cursor call, so it unblocks and exits instead
    of leaking.
    """
    try:
        con = fdb.connect(
            dsn=f"{settings.firebird_host}/{settings.firebird_port}:{settings.firebird_database}",
            user=settings.firebird_user or "SYSDBA",
            password=settings.firebird_password or "masterkey",
            charset=settings.firebird_charset,
        )
        try:
            cur = con.cursor()
            cur.execute("DELETE FROM MON$ATTACHMENTS WHERE MON$ATTACHMENT_ID = ?", (attachment_id,))
            con.commit()
        finally:
            con.close()
    except Exception as e:
        logger.warning(f"Failed to kill stuck Firebird attachment {attachment_id}: {e}")


async def run_with_timeout(func, *args, timeout: float = 55, **kwargs):
    """Run a blocking Firebird-backed call in a worker thread, bounded by
    `timeout` seconds. On timeout, also kills the call's own Firebird
    attachment (see _kill_attachment) instead of just abandoning it — a
    bare asyncio.wait_for(asyncio.to_thread(...)) only bounds the HTTP
    response, not the leaked thread/connection behind it.

    Raises asyncio.TimeoutError on timeout — callers should catch that and
    return an HTTPException(504, ...) with an actionable message.
    """
    holder: dict = {}
    token = _attachment_holder_var.set(holder)
    try:
        return await asyncio.wait_for(asyncio.to_thread(func, *args, **kwargs), timeout=timeout)
    except asyncio.TimeoutError:
        attachment_id = holder.get("attachment_id")
        if attachment_id is not None:
            try:
                await asyncio.wait_for(asyncio.to_thread(_kill_attachment, attachment_id), timeout=10)
            except Exception:
                pass
        raise
    finally:
        _attachment_holder_var.reset(token)


def _fetch_batched(cur, sql_template: str, ids: list, extra_params: tuple = (), batch: int = 1000) -> list:
    """Run `sql_template` (containing one `{ph}` IN-list placeholder) once
    per <=`batch`-item chunk of `ids`.

    Firebird rejects IN-lists over 1500 values outright, and a per-id
    correlated subquery is 20-30x slower than one batched IN query
    (measured on this DB: ~3s batched vs 60-100s correlated for a
    month/year of distinct ids) — so chunking, not correlating, is how
    every "look up N ids against a huge history table" query here works.
    The default of 1000 is for short (int) ids; string ids like DOC_NUM
    need a smaller batch since Firebird's request message block has a
    fixed size limit and long placeholder values fill it faster (measured:
    1000 string DOC_NUMs raised "block size exceeds implementation
    restriction").
    """
    rows = []
    if not ids:
        return rows
    BATCH = batch
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        placeholders = ','.join(['?'] * len(chunk))
        cur.execute(sql_template.format(ph=placeholders), (*chunk, *extra_params))
        rows.extend(cur.fetchall())
    return rows


SHOES_CODES = (
    '0', '1',
    '147.1', '147.2', '147.3', '147.4', '147.5', '147.6', '147.7',
    '147.8', '147.9', '147.10', '147.11', '147.12', '147.13', '147.14',
    '147.15', '147.16', '147.17', '147.18', '147.19', '147.20', '147.21', '147.22',
)

# "Extra" revenue categories — see FirebirdService._extra_category_rows.
# Confirmed against real order data with the business (not guessed):
CUSTOM_WORK_FOLDER_ID = 210406      # "004. Индивидуальный пошив" — sequence-parsed, see below
LEATHER_GOODS_FOLDER_ID = 210256    # "Кожгалантерея" — bags/wallets/belts sold as goods
CERTIFICATES_FOLDER_ID = 110412     # "Сертификаты"
DELIVERY_FOLDER_ID = 210257         # "07. Доставка"
KEYS_FOLDER_ID = 210                # "Ключи"
TAPOCHKI_MIXED_FOLDER_ID = 106236   # "Тапочки" — actually mixes стельки + тапочки items, split by name
ARIZONA_SLIPPERS_FOLDER_ID = 109412 # "ARIZONA ЖЕНСКИЕ" — a slippers product line
CUSTOM_MAKING_FOLDER_ID = 107249    # "Индивидуальное изготовление" — code ИНД=shoes, ИНДР=leather goods

# Within CUSTOM_WORK_FOLDER_ID, codes '0'/'1' ("Пошив обуви"/"Индивидуальный
# пошив обуви") mark the start of a shoe-tailoring job in an order — mirrors
# SHOES_CODES/_parse_shoe_pairs' 0/1 markers, but this is a separate scheme
# (plain codes, not paired with 147.x) so it's kept as its own set rather
# than merged into _PAIR_STARTERS.
_CUSTOM_WORK_SHOE_MARKERS = {'0', '1'}
_CUSTOM_WORK_INSOLE_CODE = '6'        # "Изготовление стельки"
_CUSTOM_WORK_SLIPPER_CODES = {'5', '7', '8'}   # тапочки (индив./анатомич./BK)
_CUSTOM_WORK_LEATHER_CODES = {'2', '3'}        # пошив ремня / кожгалантереи
# code '4' ("Изготовление индивидуального изделия") is deliberately
# unhandled — no clear category and zero real-world occurrences so far.

REPAIR_FOLDER_IDS = (
    215, 216, 217, 221, 326, 327, 328, 329, 330, 416, 417, 418, 419,
    108401, 108402, 110409, 110410, 110411,
    210260,  # shoe-repair-adjacent items (Босоножки/Мокасины/Кроссовки) — found missing via reconciliation against an authoritative export
    210266, 210267, 210268, 210269, 210270, 210271, 210272, 210273, 210274, 210275,
    210276, 210277, 210278, 210279, 210280, 210281, 210282, 210283, 210284, 210285,
    210286, 210287, 210288, 210289, 210290, 210291, 210292, 210293, 210294, 210295,
    210296, 210297, 210298, 210299, 210300, 210301, 210302, 210303, 210304, 210305,
    210306, 210307, 210308, 210309, 210310, 210311, 210312, 210313, 210314, 210315,
    210316, 210317, 210318, 210319, 210320, 210321, 210322, 210323, 210324, 210325,
    210326, 210327, 210328, 210329, 210330, 210331, 210332, 210333, 210334, 210335,
    210336, 210337, 210338, 210339, 210340, 210341, 210342, 210343, 210344, 210345,
    210346, 210347, 210348, 210349, 210350, 210351, 210352, 210353, 210355, 210356,
    210357, 210358, 210359, 210360, 210361, 210363, 210364, 210365, 210366,
    210377, 210378, 210379, 210380, 210381, 210382, 210383, 210384, 210385,
    210386, 210387, 210388, 210389, 210390, 210391, 210392, 210393, 210394,
    210395, 210396, 210397, 210399,
)

COSMETICS_FOLDER_IDS = (
    107, 108, 109, 110, 111, 113, 114, 115, 116, 117, 118, 119, 120,
    121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133,
    134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146,
    147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 159, 161,
    162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174,
    175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187,
    188, 189, 190, 192, 193, 194, 195, 196, 198, 199, 200, 201, 202,
    203, 204, 206, 207, 208, 209, 220, 222, 223, 229, 230, 232, 233,
    109407, 110413, 210234, 210235, 210236, 210237, 210241, 210243,
    210244, 210248, 210249, 210250, 210254, 210255, 210258, 210265,
    210398,
)

# Coarse "does this order touch category X at all" folder mapping — used
# by get_turnaround_stats/get_returns_summary to restrict which orders
# count, where (unlike _extra_category_rows/get_daily_sales) revenue
# doesn't need to be split per category, just a yes/no per order. Some
# categories share a folder (e.g. insoles/slippers both partly live in
# CUSTOM_WORK_FOLDER_ID and TAPOCHKI_MIXED_FOLDER_ID) so this is
# deliberately a little over-inclusive rather than replicating the exact
# sequence-parsing/name-matching _extra_category_rows does.
CATEGORY_FOLDER_IDS: dict[str, tuple[int, ...]] = {
    'repair': REPAIR_FOLDER_IDS,
    'cosmetics': COSMETICS_FOLDER_IDS,
    'shoes': (CUSTOM_WORK_FOLDER_ID, CUSTOM_MAKING_FOLDER_ID),
    'insoles': (CUSTOM_WORK_FOLDER_ID, TAPOCHKI_MIXED_FOLDER_ID),
    'slippers': (CUSTOM_WORK_FOLDER_ID, TAPOCHKI_MIXED_FOLDER_ID, ARIZONA_SLIPPERS_FOLDER_ID),
    'leather_goods': (CUSTOM_WORK_FOLDER_ID, LEATHER_GOODS_FOLDER_ID, CUSTOM_MAKING_FOLDER_ID),
    'certificates': (CERTIFICATES_FOLDER_ID,),
    'delivery': (DELIVERY_FOLDER_ID,),
    'keys': (KEYS_FOLDER_ID,),
}
# 'shoes' additionally lives in the 147.x tovar-code scheme (folder 210405,
# not folder-listed above since it's identified by code, not folder_id).
CATEGORY_TOVAR_CODES: dict[str, tuple[str, ...]] = {
    'shoes': SHOES_CODES,
}


def _category_exists_sql(categories: set[str], order_id_col: str = 'docs_order.id') -> tuple[str, tuple]:
    """Build an `EXISTS (...)` SQL fragment matching CATEGORY_FOLDER_IDS/
    CATEGORY_TOVAR_CODES for the given category keys (unknown keys are
    ignored). Checks both DOC_ORDER_SERVICES and DOC_ORDER_LINES since a
    category can show up as either a service or a goods line. Returns
    ("" , ()) if `categories` is empty/None (caller should skip adding
    the clause entirely in that case — matching everything is the
    no-filter case, not an always-false EXISTS).
    """
    folder_ids: set[int] = set()
    tovar_codes: set[str] = set()
    for cat in categories:
        folder_ids.update(CATEGORY_FOLDER_IDS.get(cat, ()))
        tovar_codes.update(CATEGORY_TOVAR_CODES.get(cat, ()))
    if not folder_ids and not tovar_codes:
        return "", ()

    conditions = []
    params: list = []
    if folder_ids:
        ph = ','.join(str(x) for x in folder_ids)
        conditions.append(f"t.folder_id IN ({ph})")
    if tovar_codes:
        ph = ','.join(['?'] * len(tovar_codes))
        conditions.append(f"t.code IN ({ph})")
        params.extend(tovar_codes)
    tovar_where = " OR ".join(conditions)

    sql = f"""
        (
            EXISTS (
                SELECT 1 FROM doc_order_services svc_x
                    INNER JOIN tovars_tbl t ON t.tovar_id = svc_x.tovar_id
                WHERE svc_x.doc_order_id = {order_id_col} AND ({tovar_where})
            )
            OR EXISTS (
                SELECT 1 FROM doc_order_lines lin_x
                    INNER JOIN tovars_tbl t ON t.tovar_id = lin_x.tovar_id
                WHERE lin_x.doc_order_id = {order_id_col} AND ({tovar_where})
            )
        )
    """
    return sql, tuple(params) * 2


_PAIR_STARTERS = {'0', '1'}

# Registers to show in the "Остатки по кассам" card — see get_cash_balances.
# KASSES has ~19 rows (legacy/test/franchise ones too); this is just the
# working salon list.
CASH_BALANCE_KASSA_IDS = (21057, 10969, 21067, 10564, 21066, 1172)
CASH_BALANCE_NAME_OVERRIDES = {21066: "5_Гранд Палас"}

# DOC_KASSA_BASISES.id of «Инкассация» — the only basis that moves cash
# between registers rather than in/out of the business, so the daily
# report reports it in its own column instead of mixing it into
# приход/расход (see get_daily_cash_balances).
KASSA_BASIS_INKASSATION = 93

# Widest range get_daily_cash_balances will build day rows for. The
# ledger runs back to 2013, and the report renders one row per calendar
# day including empty ones — an unbounded "всё время" request would
# build ~4600 rows of mostly nothing. Not a query-cost limit (the
# aggregates are indexed and fast at any width); a payload/readability one.
DAILY_BALANCE_MAX_DAYS = 366


def _kassa_display_name(kassa_id, raw_name) -> str | None:
    """KASSES.name resolved for a KASSA_KREDIT/KASSA_DEBET id, applying
    the same stale-name override as get_cash_balances (id 21066 is still
    labeled "5_Пассаж" in Agbis after that location was renamed)."""
    if kassa_id is None:
        return None
    try:
        kassa_id = int(kassa_id)
    except (TypeError, ValueError):
        return (raw_name or "").strip() or None
    return CASH_BALANCE_NAME_OVERRIDES.get(kassa_id, (raw_name or "").strip() or None)


def _parse_shoe_pairs(items: list[tuple]) -> list[float]:
    """Parse ordered (code, kredit) records of one order into per-pair kredit sums.

    A record with CODE in ('0','1') starts a new pair; following '147.x'
    records add to the current pair until the next starter.
    """
    pairs: list[float] = []
    current_kredit = 0.0
    in_pair = False
    for code, kredit in items:
        if code in _PAIR_STARTERS:
            if in_pair:
                pairs.append(current_kredit)
            current_kredit = 0.0
            in_pair = True
        else:
            if in_pair:
                current_kredit += kredit
    if in_pair:
        pairs.append(current_kredit)
    return pairs


# Read-only report/search endpoints that chronically hit run_with_timeout's
# 55s deadline under Firebird server contention (see TTLCache) rather than
# from being genuinely unbounded — cached briefly so retries/polling during
# a slow period reuse one in-flight query instead of piling on more.
_SEARCH_CLIENTS_CACHE_TTL = 45
_DAILY_SALES_CACHE_TTL = 45

_search_clients_cache = TTLCache(ttl=_SEARCH_CLIENTS_CACHE_TTL)
_daily_sales_cache = TTLCache(ttl=_DAILY_SALES_CACHE_TTL)


class FirebirdService:
    """Service for connecting to Firebird database and querying sales data."""

    def get_repair_sales_orders(self, year: int, month: int) -> dict[str, list[dict]]:
        """
        Get repair/dry cleaning sales by employee, broken down per order.
        Returns: {employee_code: [{doc_num: str, kredit: float}, ...]}
        """
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty repair sales")
            return {}

        start, end = _month_range(year, month)

        folder_ids = REPAIR_FOLDER_IDS

        sql = f"""
            SELECT
                users.description AS DESCRIPTION,
                docs.doc_num AS DOC_NUM,
                SUM(doc_order_services.kredit) AS SUM_KREDIT
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE
                docs.doc_date >= ?
                AND docs.doc_date < ?
                AND tovars_tbl.folder_id IN ({','.join(str(x) for x in folder_ids)})
            GROUP BY users.description, docs.doc_num
        """

        out: dict[str, list[dict]] = {}
        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql, (start, end))
                for desc, doc_num, s in cur.fetchall():
                    code = _code_from_description(desc)
                    if code and doc_num is not None:
                        out.setdefault(code, []).append({
                            "doc_num": str(doc_num),
                            "kredit": float(s or 0),
                        })
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching repair sales: {e}")

        return out

    def get_repair_sales(self, year: int, month: int) -> dict[str, float]:
        """
        Get repair/dry cleaning sales by employee for a given month.
        Returns dict: {employee_code: total_sales}
        """
        orders = self.get_repair_sales_orders(year, month)
        return {code: sum(o["kredit"] for o in os) for code, os in orders.items()}

    def get_cosmetics_sales_orders(self, year: int, month: int) -> dict[str, list[dict]]:
        """
        Get cosmetics sales by employee, broken down per order.
        Returns: {employee_code: [{doc_num: str, kredit: float}, ...]}
        """
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty cosmetics sales")
            return {}

        start, end = _month_range(year, month)

        folder_ids = COSMETICS_FOLDER_IDS

        sql = f"""
            SELECT
                users.description AS DESCRIPTION,
                docs.doc_num AS DOC_NUM,
                SUM(doc_order_lines.kredit) AS SUM_KREDIT
            FROM doc_order_lines
                INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                INNER JOIN docs_order_history ON (docs_order.id = docs_order_history.doc_order_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN users ON docs_order.creater_id = users.user_id
            WHERE
                docs_order_history.status_id = 5
                AND docs.doc_date >= ?
                AND docs.doc_date < ?
                AND tovars_tbl.folder_id IN ({','.join(str(x) for x in folder_ids)})
            GROUP BY users.description, docs.doc_num
        """

        out: dict[str, list[dict]] = {}
        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql, (start, end))
                for desc, doc_num, s in cur.fetchall():
                    code = _code_from_description(desc)
                    if code and doc_num is not None:
                        out.setdefault(code, []).append({
                            "doc_num": str(doc_num),
                            "kredit": float(s or 0),
                        })
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching cosmetics sales: {e}")

        return out

    def get_cosmetics_sales(self, year: int, month: int) -> dict[str, float]:
        """
        Get cosmetics sales by employee for a given month.
        Returns dict: {employee_code: total_sales}
        """
        orders = self.get_cosmetics_sales_orders(year, month)
        return {code: sum(o["kredit"] for o in os) for code, os in orders.items()}

    def get_shoes_data(self, year: int, month: int) -> dict[str, list[dict]]:
        """
        Get shoes sales per PAIR by employee for a given month.

        Structure in DB:
          - CODE='1' (kredit=0) marks start of a pair
          - Following CODE='147.x' records contain the actual kredit
          - All 147.x until next CODE='1' belong to that pair

        Filters by docs_order.date_out_fact and STATUS_ID=5.
        Returns: {employee_code: [{doc_num: str, kredit: float}, ...]}

        Commission rule (applied in payroll_service):
          - Sum of 147.x kredit per pair > 11000 → 1000 ₽
          - Sum of 147.x kredit per pair <= 11000 → 500 ₽
        """
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty shoes data")
            return {}

        start, end = _month_range(year, month)
        placeholders = ','.join(['?'] * len(SHOES_CODES))

        # Get all shoe-related records, ordered by ID to preserve sequence
        sql = f"""
            SELECT
                users.description AS DESCRIPTION,
                docs.doc_num AS DOC_NUM,
                tovars_tbl.code AS CODE,
                doc_order_services.kredit AS KREDIT,
                doc_order_services.id AS SERVICE_ID
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE
                docs_order.date_out_fact >= ?
                AND docs_order.date_out_fact < ?
                AND tovars_tbl.code IN ({placeholders})
                AND EXISTS (
                    SELECT 1 FROM docs_order_history
                    WHERE doc_order_id = docs_order.id
                      AND status_id = 5
                )
            ORDER BY users.description, docs.doc_num, doc_order_services.id
        """

        # Collect raw records grouped by (employee, doc_num)
        raw: dict[str, dict[str, list[tuple]]] = {}
        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql, (start, end, *SHOES_CODES))
                for desc, doc_num, code, kredit, svc_id in cur.fetchall():
                    emp_code = _code_from_description(desc)
                    if emp_code and doc_num is not None:
                        raw.setdefault(emp_code, {}).setdefault(str(doc_num), []).append(
                            (code, float(kredit or 0))
                        )
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching shoes data: {e}")
            return {}

        # Parse into pairs: CODE in ('0','1') starts a pair, sum following 147.x until next starter
        out: dict[str, list[dict]] = {}
        for emp_code, orders in raw.items():
            for doc_num, items in orders.items():
                for pair_kredit in _parse_shoe_pairs(items):
                    out.setdefault(emp_code, []).append({
                        "doc_num": doc_num,
                        "kredit": pair_kredit,
                    })

        return out

    def get_all_sales(self, year: int, month: int) -> dict[str, dict]:
        """
        Get all sales data for a month including per-DOC_NUM breakdowns.
        Returns: {employee_code: {repair: X, cosmetics: Y, shoes: Z,
                  repair_orders: [{doc_num, kredit}, ...],
                  cosmetics_orders: [{doc_num, kredit}, ...],
                  shoes_orders: [{doc_num, kredit}, ...]}}
        """
        repair_orders = self.get_repair_sales_orders(year, month)
        cosmetics_orders = self.get_cosmetics_sales_orders(year, month)
        shoes_data = self.get_shoes_data(year, month)

        repair = {code: sum(o["kredit"] for o in os) for code, os in repair_orders.items()}
        cosmetics = {code: sum(o["kredit"] for o in os) for code, os in cosmetics_orders.items()}
        # Total KREDIT per employee (for display)
        shoes_totals = {
            code: sum(o["kredit"] for o in orders)
            for code, orders in shoes_data.items()
        }

        all_codes = set(repair) | set(cosmetics) | set(shoes_data)
        return {
            code: {
                "repair": repair.get(code, 0.0),
                "cosmetics": cosmetics.get(code, 0.0),
                "shoes": shoes_totals.get(code, 0.0),
                "repair_orders": repair_orders.get(code, []),
                "cosmetics_orders": cosmetics_orders.get(code, []),
                "shoes_orders": shoes_data.get(code, []),
            }
            for code in all_codes
        }

    def get_order_breakdown(self, doc_num: str) -> dict:
        """Look up a single order by its number across repair / cosmetics / shoes.

        Returns the current seller (order creator), order date and the amount
        per category, so a sale can be reassigned to another employee.
        Read-only — never modifies Firebird.
        """
        result = {
            "doc_num": str(doc_num),
            "found": False,
            "order_date": "",
            "seller_code": None,
            "seller_name": "",
            "repair": 0.0,
            "cosmetics": 0.0,
            "shoes_total": 0.0,
            "shoes_orders": [],
        }
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - cannot look up order")
            return result

        repair_folders = ','.join(str(x) for x in REPAIR_FOLDER_IDS)
        cosmetics_folders = ','.join(str(x) for x in COSMETICS_FOLDER_IDS)
        shoes_placeholders = ','.join(['?'] * len(SHOES_CODES))

        sql_repair = f"""
            SELECT users.description, SUM(doc_order_services.kredit), MAX(docs.doc_date)
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE docs.doc_num = ?
                AND tovars_tbl.folder_id IN ({repair_folders})
                AND docs_order.id = (
                    SELECT MAX(do2.id) FROM docs_order do2 WHERE do2.doc_id = docs_order.doc_id
                )
            GROUP BY users.description
        """
        sql_cosmetics = f"""
            SELECT users.description, SUM(doc_order_lines.kredit), MAX(docs.doc_date)
            FROM doc_order_lines
                INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE docs.doc_num = ?
                AND tovars_tbl.folder_id IN ({cosmetics_folders})
                AND docs_order.id = (
                    SELECT MAX(do2.id) FROM docs_order do2 WHERE do2.doc_id = docs_order.doc_id
                )
                AND EXISTS (
                    SELECT 1 FROM docs_order_history
                    WHERE doc_order_id = docs_order.id AND status_id = 5
                )
            GROUP BY users.description
        """
        sql_shoes = f"""
            SELECT users.description, tovars_tbl.code, doc_order_services.kredit, doc_order_services.id
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE docs.doc_num = ?
                AND tovars_tbl.code IN ({shoes_placeholders})
                AND docs_order.id = (
                    SELECT MAX(do2.id) FROM docs_order do2 WHERE do2.doc_id = docs_order.doc_id
                )
                AND EXISTS (
                    SELECT 1 FROM docs_order_history
                    WHERE doc_order_id = docs_order.id AND status_id = 5
                )
            ORDER BY doc_order_services.id
        """

        descriptions: list[str] = []

        def _note_date(d) -> None:
            if d and not result["order_date"]:
                result["order_date"] = d.isoformat() if hasattr(d, "isoformat") else str(d)

        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql_repair, (doc_num,))
                for desc, s, d in cur.fetchall():
                    result["repair"] += float(s or 0)
                    descriptions.append(desc)
                    _note_date(d)
                cur.execute(sql_cosmetics, (doc_num,))
                for desc, s, d in cur.fetchall():
                    result["cosmetics"] += float(s or 0)
                    descriptions.append(desc)
                    _note_date(d)
                cur.execute(sql_shoes, (doc_num, *SHOES_CODES))
                shoe_items: list[tuple] = []
                for desc, code, kredit, _svc_id in cur.fetchall():
                    descriptions.append(desc)
                    shoe_items.append((code, float(kredit or 0)))
                for pair_kredit in _parse_shoe_pairs(shoe_items):
                    result["shoes_orders"].append({"doc_num": str(doc_num), "kredit": pair_kredit})
                result["shoes_total"] = sum(o["kredit"] for o in result["shoes_orders"])
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching order {doc_num}: {e}")
            return result

        for desc in descriptions:
            code = _code_from_description(desc)
            if code:
                result["seller_code"] = code
                result["seller_name"] = (desc or "").strip()
                break

        result["found"] = bool(
            result["repair"] or result["cosmetics"] or result["shoes_orders"]
        )
        return result

    @staticmethod
    def _decode_text(v) -> str:
        if isinstance(v, bytes):
            try:
                return v.decode("utf-8")
            except UnicodeDecodeError:
                return v.decode("cp1251", errors="replace")
        return v or ""

    def _sclad_names(self, cur) -> dict[int, str]:
        """id -> decoded NAME for every row in SCLADS (Agbis warehouse list).

        Used to give a readable label to orders whose doc_num doesn't
        resolve to a registered salon, via DOCS_ORDER.SCLAD_KREDIT_ID.
        """
        cur.execute("SELECT id, name FROM sclads")
        return {sid: self._decode_text(name).strip() for sid, name in cur.fetchall()}

    def get_sclads_list(self) -> list[dict]:
        """All Agbis SCLADS (id, name) for the Salons-page binding dropdown."""
        if not FIREBIRD_AVAILABLE:
            return []
        try:
            con = _connect()
            try:
                cur = con.cursor()
                names = self._sclad_names(cur)
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching sclads list: {e}")
            return []
        return sorted(
            [{"id": sid, "name": name} for sid, name in names.items() if name],
            key=lambda s: s["name"],
        )

    def _extra_category_rows(self, cur, date_from: date, date_to: date) -> list[tuple]:
        """Revenue outside repair/cosmetics/(147.x)shoes that used to be
        invisible on the Sales Analytics page entirely — see the folder-id
        constants above. Every rule here was confirmed against real order
        data with the business, not guessed from folder names.

        Returns (doc_date, description, doc_num, category, kredit,
        sclad_kredit_id) tuples, category in {"shoes", "insoles",
        "slippers", "leather_goods", "certificates", "delivery", "keys"}
        — same shape as the sql_repair/sql_cosmetics/sql_shoes rows
        get_daily_sales already loops over, so callers can reuse their
        existing per-row handling. `sclad_kredit_id` is DOCS_ORDER's
        "Склад приёма" (reception warehouse) — used by
        get_department_comparison to label orders whose doc_num doesn't
        resolve to a registered salon.
        """
        out: list[tuple] = []

        # -- CUSTOM_WORK_FOLDER_ID: sequence-parsed per order, like
        # _parse_shoe_pairs but for this folder's own 0/1 marker scheme.
        # "Изготовление стельки" only counts as shoes revenue if it comes
        # after a "Пошив обуви" marker in the SAME order; otherwise it's a
        # standalone "Стельки" sale.
        cur.execute("""
            SELECT docs.doc_date, docs.doc_num, users.description, tovars_tbl.code,
                   doc_order_services.kredit, doc_order_services.doc_order_id, doc_order_services.id,
                   docs_order.sclad_kredit_id
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE docs.doc_date >= ? AND docs.doc_date <= ? AND tovars_tbl.folder_id = ?
            ORDER BY doc_order_services.doc_order_id, doc_order_services.id
        """, (date_from, date_to, CUSTOM_WORK_FOLDER_ID))
        by_order: dict = {}
        for doc_date, doc_num, desc, code, kredit, order_id, _svc_id, sclad_id in cur.fetchall():
            entry = by_order.setdefault(order_id, {"doc_date": doc_date, "doc_num": doc_num, "desc": desc, "sclad_id": sclad_id, "items": []})
            entry["items"].append((self._decode_text(code).strip(), float(kredit or 0)))
        for order in by_order.values():
            in_shoe_context = False
            for code, kredit in order["items"]:
                if code in _CUSTOM_WORK_SHOE_MARKERS:
                    in_shoe_context = True
                    if kredit:
                        out.append((order["doc_date"], order["desc"], order["doc_num"], "shoes", kredit, order["sclad_id"]))
                elif code == _CUSTOM_WORK_INSOLE_CODE:
                    cat = "shoes" if in_shoe_context else "insoles"
                    out.append((order["doc_date"], order["desc"], order["doc_num"], cat, kredit, order["sclad_id"]))
                elif code in _CUSTOM_WORK_SLIPPER_CODES:
                    out.append((order["doc_date"], order["desc"], order["doc_num"], "slippers", kredit, order["sclad_id"]))
                elif code in _CUSTOM_WORK_LEATHER_CODES:
                    out.append((order["doc_date"], order["desc"], order["doc_num"], "leather_goods", kredit, order["sclad_id"]))
                # code '4' — see module-level comment, deliberately skipped.

        # -- DELIVERY_FOLDER_ID: plain services-side sum --
        cur.execute("""
            SELECT docs.doc_date, docs.doc_num, users.description, SUM(doc_order_services.kredit), docs_order.sclad_kredit_id
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE docs.doc_date >= ? AND docs.doc_date <= ? AND tovars_tbl.folder_id = ?
            GROUP BY docs.doc_date, docs.doc_num, users.description, docs_order.sclad_kredit_id
        """, (date_from, date_to, DELIVERY_FOLDER_ID))
        for d, doc_num, desc, s, sclad_id in cur.fetchall():
            out.append((d, desc, doc_num, "delivery", float(s or 0), sclad_id))

        # -- plain goods-side (DOC_ORDER_LINES) folder sums --
        def _lines_folder_sum(folder_id: int, category: str) -> None:
            cur.execute("""
                SELECT docs.doc_date, docs.doc_num, users.description, SUM(doc_order_lines.kredit), docs_order.sclad_kredit_id
                FROM doc_order_lines
                    INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                    INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                    INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
                    INNER JOIN users ON (docs_order.creater_id = users.user_id)
                WHERE docs.doc_date >= ? AND docs.doc_date <= ? AND tovars_tbl.folder_id = ?
                GROUP BY docs.doc_date, docs.doc_num, users.description, docs_order.sclad_kredit_id
            """, (date_from, date_to, folder_id))
            for d, doc_num, desc, s, sclad_id in cur.fetchall():
                out.append((d, desc, doc_num, category, float(s or 0), sclad_id))

        _lines_folder_sum(LEATHER_GOODS_FOLDER_ID, "leather_goods")
        _lines_folder_sum(CERTIFICATES_FOLDER_ID, "certificates")
        _lines_folder_sum(KEYS_FOLDER_ID, "keys")
        _lines_folder_sum(ARIZONA_SLIPPERS_FOLDER_ID, "slippers")

        # -- TAPOCHKI_MIXED_FOLDER_ID: mixes "Стельки..." and "Тапочки..."
        # item names in the same folder — split by name prefix.
        cur.execute("""
            SELECT docs.doc_date, docs.doc_num, users.description, tovars_tbl.name, doc_order_lines.kredit, docs_order.sclad_kredit_id
            FROM doc_order_lines
                INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE docs.doc_date >= ? AND docs.doc_date <= ? AND tovars_tbl.folder_id = ?
        """, (date_from, date_to, TAPOCHKI_MIXED_FOLDER_ID))
        for d, doc_num, desc, name, kredit, sclad_id in cur.fetchall():
            cat = "insoles" if self._decode_text(name).strip().lower().startswith("стельк") else "slippers"
            out.append((d, desc, doc_num, cat, float(kredit or 0), sclad_id))

        # -- CUSTOM_MAKING_FOLDER_ID: code ИНД=shoes, ИНДР=leather goods --
        cur.execute("""
            SELECT docs.doc_date, docs.doc_num, users.description, tovars_tbl.code, doc_order_lines.kredit, docs_order.sclad_kredit_id
            FROM doc_order_lines
                INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE docs.doc_date >= ? AND docs.doc_date <= ? AND tovars_tbl.folder_id = ?
        """, (date_from, date_to, CUSTOM_MAKING_FOLDER_ID))
        for d, doc_num, desc, code, kredit, sclad_id in cur.fetchall():
            cat = "leather_goods" if self._decode_text(code).strip().upper() == "ИНДР" else "shoes"
            out.append((d, desc, doc_num, cat, float(kredit or 0), sclad_id))

        return out

    def get_daily_sales(self, date_from: date, date_to: date, salon_ids: list[str] | None = None) -> list[dict]:
        """
        Get daily sales by employee for a date range, broken out by
        category. Returns list of dicts: {date, code, description, repair,
        cosmetics, shoes, insoles, slippers, leather_goods, certificates,
        delivery, keys, total} — see _extra_category_rows for what feeds
        the categories past "shoes" (all previously invisible on this
        page; rules confirmed with the business, not guessed).

        `salon_ids` (Salon.id values, e.g. from GET /api/salons/) restricts
        to orders resolved to one of those salons via the doc_num suffix
        (same attribution as get_department_comparison / "ФОТ по салонам").
        Orders that don't resolve to any salon are excluded when a filter
        is active — we can't confirm they belong to the selected ones.

        Cached for _DAILY_SALES_CACHE_TTL — see TTLCache's docstring for
        why (this endpoint was one of the two chronically hitting the 55s
        Firebird timeout under load).
        """
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty daily sales")
            return []
        salon_key = tuple(sorted(salon_ids)) if salon_ids else None
        return _daily_sales_cache.get_or_compute(
            (date_from, date_to, salon_key),
            lambda: self._get_daily_sales_uncached(date_from, date_to, salon_ids),
        )

    def _get_daily_sales_uncached(self, date_from: date, date_to: date, salon_ids: list[str] | None) -> list[dict]:
        salon_filter = set(salon_ids) if salon_ids else None

        # Was a hardcoded duplicate of the module-level REPAIR_FOLDER_IDS /
        # COSMETICS_FOLDER_IDS — drifted out of sync with them once already
        # (see 210260 below), which silently reintroduces the exact
        # Обзор≠Салоны mismatch bug fixed earlier. Reference the module
        # constants instead so there's only one list to update.
        repair_folder_ids = REPAIR_FOLDER_IDS
        cosmetics_folder_ids = COSMETICS_FOLDER_IDS

        shoes_sales_codes = tuple(c for c in SHOES_CODES if c not in ('0', '1'))
        shoes_placeholders = ','.join(['?'] * len(shoes_sales_codes))

        # key: (date_str, code) → {date, code, description, repair, cosmetics, shoes}
        result: dict[tuple, dict] = {}

        def _add(date_val, desc: str, amount, category: str) -> None:
            label = (desc or "").strip()
            # Some order creators in Agbis (sales-department/marketing
            # accounts, e.g. "Карина Т.") never got the trailing 4-digit
            # code regular masters have — their revenue used to be silently
            # dropped here instead of just not resolving to a payroll
            # employee. Fall back to the raw Agbis name as the row's key;
            # empName() on the frontend already renders an unknown "code"
            # as-is, so this surfaces correctly with no frontend change.
            code = _code_from_description(desc) or label or "—"
            date_str = date_val.isoformat() if hasattr(date_val, "isoformat") else str(date_val)
            key = (date_str, code)
            if key not in result:
                result[key] = {
                    "date": date_str,
                    "code": code,
                    "description": label,
                    "repair": 0.0,
                    "cosmetics": 0.0,
                    "shoes": 0.0,
                    "insoles": 0.0,
                    "slippers": 0.0,
                    "leather_goods": 0.0,
                    "certificates": 0.0,
                    "delivery": 0.0,
                    "keys": 0.0,
                }
            result[key][category] += float(amount or 0)

        # doc_num is only selected/grouped-on so a salon filter can resolve
        # it per row below — dropped again once resolved, same aggregation
        # grain (date, employee) as before when no filter is active.
        sql_repair = f"""
            SELECT
                docs.doc_date,
                users.description,
                docs.doc_num,
                SUM(doc_order_services.kredit)
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE
                docs.doc_date >= ?
                AND docs.doc_date <= ?
                AND tovars_tbl.folder_id IN ({','.join(str(x) for x in repair_folder_ids)})
            GROUP BY docs.doc_date, users.description, docs.doc_num
        """

        # No status_id filter here — analytics counts revenue as soon as
        # it's on the order, same as repair/shoes, not just once it reaches
        # "Исполнен". (Also avoids the docs_order_history JOIN fan-out: an
        # order can pass through status 5 more than once — e.g. reopened
        # and re-completed — which used to multiply-count its lines.)
        sql_cosmetics = f"""
            SELECT
                docs.doc_date,
                users.description,
                docs.doc_num,
                SUM(doc_order_lines.kredit)
            FROM doc_order_lines
                INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE
                docs.doc_date >= ?
                AND docs.doc_date <= ?
                AND tovars_tbl.folder_id IN ({','.join(str(x) for x in cosmetics_folder_ids)})
            GROUP BY docs.doc_date, users.description, docs.doc_num
        """

        sql_shoes = f"""
            SELECT
                CAST(docs.doc_date AS DATE),
                users.description,
                docs.doc_num,
                SUM(doc_order_services.kredit)
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE
                CAST(docs.doc_date AS DATE) >= ?
                AND CAST(docs.doc_date AS DATE) <= ?
                AND tovars_tbl.code IN ({shoes_placeholders})
            GROUP BY CAST(docs.doc_date AS DATE), users.description, docs.doc_num
        """

        try:
            con = _connect()
            try:
                cur = con.cursor()
                with _SalonResolver() as resolve_salon:
                    def _keep(doc_num, doc_date) -> bool:
                        if salon_filter is None:
                            return True
                        return resolve_salon(doc_num, doc_date) in salon_filter

                    cur.execute(sql_repair, (date_from, date_to))
                    for d, desc, doc_num, s in cur.fetchall():
                        if _keep(doc_num, d):
                            _add(d, desc, s, "repair")
                    cur.execute(sql_cosmetics, (date_from, date_to))
                    for d, desc, doc_num, s in cur.fetchall():
                        if _keep(doc_num, d):
                            _add(d, desc, s, "cosmetics")
                    cur.execute(sql_shoes, (date_from, date_to, *shoes_sales_codes))
                    for d, desc, doc_num, s in cur.fetchall():
                        if d is not None and _keep(doc_num, d):
                            _add(d, desc, s, "shoes")
                    for d, desc, doc_num, category, s, _sclad_id in self._extra_category_rows(cur, date_from, date_to):
                        if d is not None and _keep(doc_num, d):
                            _add(d, desc, s, category)
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching daily sales: {e}")
            # Re-raise instead of falling through to the return below with
            # whatever partial `result` was accumulated — see the matching
            # comment in _search_clients_uncached for why: this function is
            # cached by _daily_sales_cache.get_or_compute(), and a swallowed
            # error here would get cached as a "successful" (empty/partial)
            # result for _DAILY_SALES_CACHE_TTL seconds instead of letting
            # the next caller retry fresh.
            raise

        extra_keys = ("insoles", "slippers", "leather_goods", "certificates", "delivery", "keys")
        return [
            {**v, "total": v["repair"] + v["cosmetics"] + v["shoes"] + sum(v[k] for k in extra_keys)}
            for v in sorted(result.values(), key=lambda x: (x["date"], x["code"]))
        ]


    def get_client_retention(self, date_from: date, date_to: date, salon_ids: list[str] | None = None) -> dict:
        """New-vs-returning client breakdown for a date range.

        A client is "returning" if their first-ever order (across all
        history) predates date_from, "new" otherwise. The first-ever-order
        lookup is a single ungrouped-by-date full scan (~3s regardless of
        range) rather than one lookup per client — a per-client correlated
        subquery was measured at 60-100s for a month/year range because it
        re-executes the MIN(doc_date) query once per distinct client.

        `salon_ids` restricts to orders resolved to one of those salons —
        see get_daily_sales for the attribution rule and its caveats.
        """
        empty = {"total_clients": 0, "new_clients": 0, "returning_clients": 0, "repeat_rate": 0.0}
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty client retention")
            return empty
        salon_filter = set(salon_ids) if salon_ids else None

        sql_active = """
            SELECT d.contragent_id, do.id, d.doc_num, d.doc_date
            FROM docs d
                INNER JOIN docs_order do ON (do.doc_id = d.doc_id)
            WHERE
                d.doc_date >= ?
                AND d.doc_date <= ?
                AND d.contragent_id IS NOT NULL
        """
        sql_first_order = """
            SELECT d.contragent_id, MIN(d.doc_date)
            FROM docs d
                INNER JOIN docs_order do ON (do.doc_id = d.doc_id)
            WHERE d.contragent_id IS NOT NULL
            GROUP BY d.contragent_id
        """

        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql_active, (date_from, date_to))
                active_rows = cur.fetchall()
                if not active_rows:
                    return empty

                cur.execute(sql_first_order)
                first_order = dict(cur.fetchall())
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching client retention: {e}")
            return empty

        active_ids: set = set()
        with _SalonResolver() as resolve_salon:
            for contragent_id, _order_id, doc_num, doc_date in active_rows:
                if salon_filter is not None and resolve_salon(doc_num, doc_date) not in salon_filter:
                    continue
                active_ids.add(contragent_id)

        total = len(active_ids)
        returning = sum(
            1 for contragent_id in active_ids
            if (first_order.get(contragent_id) or date_from) < date_from
        )
        new_clients = total - returning
        return {
            "total_clients": total,
            "new_clients": new_clients,
            "returning_clients": returning,
            "repeat_rate": round(returning / total * 100, 1) if total else 0.0,
        }

    @staticmethod
    def _order_revenue_rows(cur, date_from: date | None = None, date_to: date | None = None,
                             contragent_id: int | None = None) -> list[tuple]:
        """Shared repair+cosmetics+shoes order-level revenue query.

        Returns merged (contragent_id, doc_num, doc_date, revenue) rows —
        used by client-profile and churn detection, which both need
        per-client order history rather than the per-employee/per-category
        totals get_margin_summary/get_department_comparison compute.
        """
        conditions = []
        params: list = []
        if date_from is not None:
            conditions.append("docs.doc_date >= ?")
            params.append(date_from)
        if date_to is not None:
            conditions.append("docs.doc_date <= ?")
            params.append(date_to)
        if contragent_id is not None:
            conditions.append("docs.contragent_id = ?")
            params.append(contragent_id)
        where_extra = (" AND " + " AND ".join(conditions)) if conditions else ""

        repair_folders = ','.join(str(x) for x in REPAIR_FOLDER_IDS)
        cosmetics_folders = ','.join(str(x) for x in COSMETICS_FOLDER_IDS)
        shoes_sales_codes = tuple(c for c in SHOES_CODES if c not in ('0', '1'))
        shoes_placeholders = ','.join(['?'] * len(shoes_sales_codes))

        sql_repair = f"""
            SELECT docs.contragent_id, docs.doc_num, docs.doc_date, SUM(doc_order_services.kredit)
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
            WHERE tovars_tbl.folder_id IN ({repair_folders}){where_extra}
            GROUP BY docs.contragent_id, docs.doc_num, docs.doc_date
        """
        sql_cosmetics = f"""
            SELECT docs.contragent_id, docs.doc_num, docs.doc_date, SUM(doc_order_lines.kredit)
            FROM doc_order_lines
                INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                INNER JOIN docs_order_history ON (docs_order.id = docs_order_history.doc_order_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
            WHERE docs_order_history.status_id = 5
                AND tovars_tbl.folder_id IN ({cosmetics_folders}){where_extra}
            GROUP BY docs.contragent_id, docs.doc_num, docs.doc_date
        """
        sql_shoes = f"""
            SELECT docs.contragent_id, docs.doc_num, docs.doc_date, SUM(doc_order_services.kredit)
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
            WHERE tovars_tbl.code IN ({shoes_placeholders}){where_extra}
            GROUP BY docs.contragent_id, docs.doc_num, docs.doc_date
        """

        cur.execute(sql_repair, tuple(params))
        rows = list(cur.fetchall())
        cur.execute(sql_cosmetics, tuple(params))
        rows += cur.fetchall()
        cur.execute(sql_shoes, (*shoes_sales_codes, *params))
        rows += cur.fetchall()
        return rows

    def search_clients(self, query: str, limit: int = 20) -> list[dict]:
        """Search CONTRAGENTS by name, phone, or order number (DOCS.DOC_NUM).

        Excludes "Розница <салон>" accounts — generic walk-in buckets used
        when no specific client is registered (one such account can carry
        thousands of anonymous orders), which would swamp real clients in
        search results and make no sense in a client-level CRM.

        The order-number branch only runs when the query has digits in it
        (order numbers are numeric, e.g. "34247" or "34247-7") — skipping
        it for pure-name queries avoids a pointless extra table scan.

        Cached for _SEARCH_CLIENTS_CACHE_TTL — see TTLCache's docstring for
        why (this endpoint was one of the two chronically hitting the 55s
        Firebird timeout under load).
        """
        if not FIREBIRD_AVAILABLE or not (query or "").strip():
            return []
        q = query.strip()
        return _search_clients_cache.get_or_compute(
            (q, limit), lambda: self._search_clients_uncached(q, limit)
        )

    def _search_clients_uncached(self, q: str, limit: int) -> list[dict]:
        sql_name = """
            SELECT FIRST ? contr_id, name, teleph_cell
            FROM contragents
            WHERE (UPPER(name) LIKE UPPER(?) OR teleph_cell LIKE ?)
                AND UPPER(name) NOT STARTING WITH 'РОЗНИЦА'
            ORDER BY name
        """
        sql_order = """
            SELECT FIRST ? c.contr_id, c.name, c.teleph_cell
            FROM docs d
                INNER JOIN contragents c ON c.contr_id = d.contragent_id
            WHERE d.doc_num LIKE ?
                AND UPPER(c.name) NOT STARTING WITH 'РОЗНИЦА'
            ORDER BY d.doc_date DESC
        """
        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql_name, (limit, f"%{q}%", f"%{q}%"))
                rows = list(cur.fetchall())
                if any(ch.isdigit() for ch in q):
                    cur.execute(sql_order, (limit, f"%{q}%"))
                    rows += cur.fetchall()
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error searching clients: {e}")
            # Re-raise instead of returning [] — this function is called
            # through _search_clients_cache.get_or_compute(); swallowing the
            # error here would make compute() "succeed" with an empty list,
            # which TTLCache would then cache as a legitimate result for
            # _SEARCH_CLIENTS_CACHE_TTL seconds. That's exactly backwards
            # for the run_with_timeout+_kill_attachment case this cache was
            # built to survive: a killed attachment raises here, and an
            # empty-but-cached "no results" would be served to every other
            # caller for the rest of the TTL instead of a fresh retry.
            raise

        seen: set[int] = set()
        results: list[dict] = []
        for cid, name, phone in rows:
            if cid in seen:
                continue
            seen.add(cid)
            results.append({"contragent_id": cid, "name": (name or "").strip(), "phone": (phone or "").strip() or None})
        return results[:limit]

    def get_client_profile(self, contragent_id: int) -> dict | None:
        """Full order history + LTV/avg-check/last-visit for one client.

        Also pulls the client's answer to the "Опрос" combo field on the
        Agbis client card (ADDON_TYPES.ID=106253, DESCR='Опрос',
        TABLE_NAME='CONTRAGENTS') — this is the acquisition-channel
        dropdown ("проходил мимо" / "ЯНДЕКС поиск" / "рекомендация
        знакомых" / ...), not the separate POLLS/FORM_POLL survey system
        (that one turned out to be a near-dead legacy feature with a
        couple dozen answers total). ADDON_CONTRAGS.LINE_ID is the
        CONTRAGENTS.CONTR_ID, one row per client for this addon type;
        VALUE_STR already carries the display text, no lookup needed.
        """
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning no client profile")
            return None

        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(
                    "SELECT contr_id, name, teleph_cell FROM contragents WHERE contr_id = ?",
                    (contragent_id,),
                )
                contact = cur.fetchone()
                if contact is None:
                    return None
                rows = self._order_revenue_rows(cur, contragent_id=contragent_id)
                cur.execute(
                    "SELECT value_str FROM addon_contrags WHERE line_id = ? AND addon_type_id = 106253",
                    (contragent_id,),
                )
                acquisition = cur.fetchone()
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching client profile: {e}")
            return None

        orders: dict[str, dict] = {}
        for _cid, doc_num, doc_date, revenue in rows:
            key = str(doc_num)
            entry = orders.setdefault(key, {"doc_num": key, "date": doc_date, "amount": 0.0})
            entry["amount"] += float(revenue or 0)

        order_list = sorted(orders.values(), key=lambda o: o["date"])
        total_spent = sum(o["amount"] for o in order_list)
        order_count = len(order_list)

        return {
            "contragent_id": contragent_id,
            "name": (contact[1] or "").strip(),
            "phone": (contact[2] or "").strip() or None,
            "order_count": order_count,
            "total_spent": round(total_spent, 2),
            "avg_check": round(total_spent / order_count, 2) if order_count else 0.0,
            "first_order_date": order_list[0]["date"].isoformat() if order_list else None,
            "last_order_date": order_list[-1]["date"].isoformat() if order_list else None,
            "acquisition_channel": (acquisition[0] or "").strip() if acquisition and acquisition[0] else None,
            "orders": [
                {"doc_num": o["doc_num"], "date": o["date"].isoformat(), "amount": round(o["amount"], 2)}
                for o in reversed(order_list)
            ],
        }

    def get_order_items(self, contragent_id: int, doc_num: str) -> list[dict]:
        """Line items (services + goods) inside one client order.

        Mirrors the two item tables _order_revenue_rows sums over —
        DOC_ORDER_SERVICES (repair/shoes services) and DOC_ORDER_LINES
        (cosmetics/retail goods) — but here without the folder_id/code
        filters, since this is "what's actually in this order" rather
        than the category-scoped revenue rollup. DOC_ORDER_LINES has its
        own free-text TOVAR_DESCRIPT (used when a line isn't tied to a
        catalog item), hence the COALESCE with TOVARS_TBL.NAME.
        """
        if not FIREBIRD_AVAILABLE:
            return []
        sql = """
            SELECT tv.name, dos.qty_kredit, dos.kredit, 'service'
            FROM docs d
                INNER JOIN docs_order dor ON dor.doc_id = d.doc_id
                INNER JOIN doc_order_services dos ON dos.doc_order_id = dor.id
                INNER JOIN tovars_tbl tv ON tv.tovar_id = dos.tovar_id
            WHERE d.contragent_id = ? AND d.doc_num = ?

            UNION ALL

            SELECT COALESCE(tv.name, dol.tovar_descript), dol.qty_kredit, dol.kredit, 'good'
            FROM docs d
                INNER JOIN docs_order dor ON dor.doc_id = d.doc_id
                INNER JOIN doc_order_lines dol ON dol.doc_order_id = dor.id
                LEFT JOIN tovars_tbl tv ON tv.tovar_id = dol.tovar_id
            WHERE d.contragent_id = ? AND d.doc_num = ?
        """
        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql, (contragent_id, doc_num, contragent_id, doc_num))
                rows = cur.fetchall()
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching order items: {e}")
            return []

        return [
            {
                "name": (name or "").strip() or "—",
                "qty": float(qty) if qty is not None else None,
                "amount": round(float(amount or 0), 2),
                "kind": kind,
            }
            for name, qty, amount, kind in rows
        ]

    def get_churning_clients(self, lookback_days: int = 365, min_orders: int = 3, limit: int = 200) -> list[dict]:
        """Clients who used to order regularly and have gone quiet.

        "Regular" = at least `min_orders` orders in the trailing
        `lookback_days`. "Gone quiet" = no order since at least
        max(2 x their own average gap between orders, 45 days) — a
        personalized threshold rather than one fixed cutoff for everyone,
        since a client who used to order every 10 days going silent for
        30 is a very different signal than one who always ordered every
        60 days.

        This is a reporting list only — no message is sent from here (no
        SMS/Telegram send capability exists in this project yet).
        """
        empty: list[dict] = []
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning no churning clients")
            return empty

        today = date.today()
        lookback_start = today - timedelta(days=lookback_days)

        try:
            con = _connect()
            try:
                cur = con.cursor()
                rows = self._order_revenue_rows(cur, date_from=lookback_start, date_to=today)
                if not rows:
                    return empty

                client_ids = sorted({cid for cid, *_ in rows if cid is not None})
                sql_contacts = """
                    SELECT contr_id, name, teleph_cell FROM contragents
                    WHERE contr_id IN ({ph}) AND UPPER(name) NOT STARTING WITH 'РОЗНИЦА'
                """
                contact_rows = _fetch_batched(cur, sql_contacts, client_ids)
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching churning clients: {e}")
            return empty

        contacts = {cid: (name, phone) for cid, name, phone in contact_rows}

        by_client: dict[int, dict] = {}
        for cid, doc_num, doc_date, revenue in rows:
            if cid not in contacts:  # excludes "Розница" buckets and orders with no linked client
                continue
            entry = by_client.setdefault(cid, {"dates": set(), "revenue": 0.0})
            entry["dates"].add(doc_date)
            entry["revenue"] += float(revenue or 0)

        result = []
        for cid, entry in by_client.items():
            dates = sorted(entry["dates"])
            order_count = len(dates)
            if order_count < min_orders:
                continue
            span_days = (dates[-1] - dates[0]).days
            avg_gap = span_days / (order_count - 1) if order_count > 1 else 0
            days_since_last = (today - dates[-1]).days
            overdue_threshold = max(avg_gap * 2, 45)
            if days_since_last <= overdue_threshold:
                continue
            name, phone = contacts[cid]
            result.append({
                "contragent_id": cid,
                "name": (name or "").strip(),
                "phone": (phone or "").strip() or None,
                "order_count": order_count,
                "total_spent": round(entry["revenue"], 2),
                "avg_gap_days": round(avg_gap, 1),
                "last_order_date": dates[-1].isoformat(),
                "days_since_last_order": days_since_last,
            })

        result.sort(key=lambda c: c["total_spent"], reverse=True)
        return result[:limit]

    def get_margin_summary(self, date_from: date, date_to: date, salon_ids: list[str] | None = None) -> dict:
        """Gross margin by category and by employee for a date range.

        Cost is the most recent warehouse-receipt price (DOC_SCLAD_LINES,
        DOC_TYPE=1 "Приход") at or before date_to for each sold TOVAR_ID.
        Shoes are deliberately excluded: their commission is computed on
        paired 0/1+147.x records (see SHOES_CODES/_parse_shoe_pairs), which
        isn't a per-unit cost-of-goods figure the same way repair/cosmetics
        are. Repair-category items are mostly labor (cleaning/repair
        services) with no purchase record at all — those come back with
        cost=0, which is correct (their real cost is payroll, tracked
        elsewhere), not a data gap.

        `salon_ids` restricts to orders resolved to one of those salons —
        see get_daily_sales for the attribution rule and its caveats.
        """
        empty_cat = {"revenue": 0.0, "cost": 0.0, "margin": 0.0, "margin_pct": 0.0}
        empty = {
            "categories": {"repair": dict(empty_cat), "cosmetics": dict(empty_cat)},
            "total": dict(empty_cat),
            "by_employee": [],
            "unpriced_items": 0,
        }
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty margin summary")
            return empty
        salon_filter = set(salon_ids) if salon_ids else None

        repair_folders = ','.join(str(x) for x in REPAIR_FOLDER_IDS)
        cosmetics_folders = ','.join(str(x) for x in COSMETICS_FOLDER_IDS)

        sql_repair = f"""
            SELECT users.description, tovars_tbl.tovar_id, docs.doc_date, docs.doc_num,
                   SUM(doc_order_services.kredit), SUM(doc_order_services.qty_kredit)
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE
                docs.doc_date >= ? AND docs.doc_date <= ?
                AND tovars_tbl.folder_id IN ({repair_folders})
            GROUP BY users.description, tovars_tbl.tovar_id, docs.doc_date, docs.doc_num
        """
        # No status_id filter — see get_daily_sales' sql_cosmetics comment.
        sql_cosmetics = f"""
            SELECT users.description, tovars_tbl.tovar_id, docs.doc_date, docs.doc_num,
                   SUM(doc_order_lines.kredit), SUM(doc_order_lines.qty_kredit)
            FROM doc_order_lines
                INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN users ON docs_order.creater_id = users.user_id
            WHERE
                docs.doc_date >= ? AND docs.doc_date <= ?
                AND tovars_tbl.folder_id IN ({cosmetics_folders})
            GROUP BY users.description, tovars_tbl.tovar_id, docs.doc_date, docs.doc_num
        """
        sql_cost = """
            SELECT tovar_id, price, dl_date
            FROM doc_sclad_lines
            WHERE tovar_id IN ({ph}) AND doc_type = 1 AND dl_date <= ?
            ORDER BY tovar_id, dl_date DESC
        """

        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql_repair, (date_from, date_to))
                repair_rows = cur.fetchall()
                cur.execute(sql_cosmetics, (date_from, date_to))
                cosmetics_rows = cur.fetchall()

                tovar_ids = sorted({r[1] for r in repair_rows} | {r[1] for r in cosmetics_rows})
                cost_rows = _fetch_batched(cur, sql_cost, tovar_ids, (date_to,))
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching margin summary: {e}")
            return empty

        unit_cost: dict[int, float] = {}
        for tovar_id, price, _dl_date in cost_rows:
            if tovar_id not in unit_cost:  # first row per tovar_id = latest (ORDER BY ... DESC)
                unit_cost[tovar_id] = float(price or 0)
        unpriced_items = len(tovar_ids) - len(unit_cost)

        by_emp: dict[str, dict] = {}

        with _SalonResolver() as resolve_salon:
            def _accumulate(rows, category: str) -> None:
                for desc, tovar_id, doc_date, doc_num, revenue, qty in rows:
                    if salon_filter is not None and resolve_salon(doc_num, doc_date) not in salon_filter:
                        continue
                    code = _code_from_description(desc)
                    if not code:
                        continue
                    cost = float(qty or 0) * unit_cost.get(tovar_id, 0.0)
                    entry = by_emp.setdefault(code, {
                        "code": code, "repair_revenue": 0.0, "repair_cost": 0.0,
                        "cosmetics_revenue": 0.0, "cosmetics_cost": 0.0,
                    })
                    entry[f"{category}_revenue"] += float(revenue or 0)
                    entry[f"{category}_cost"] += cost

            _accumulate(repair_rows, "repair")
            _accumulate(cosmetics_rows, "cosmetics")

        categories = {"repair": dict(empty_cat), "cosmetics": dict(empty_cat)}
        for cat in ("repair", "cosmetics"):
            rev = sum(e[f"{cat}_revenue"] for e in by_emp.values())
            cost = sum(e[f"{cat}_cost"] for e in by_emp.values())
            categories[cat] = {
                "revenue": rev, "cost": cost, "margin": rev - cost,
                "margin_pct": round((rev - cost) / rev * 100, 1) if rev else 0.0,
            }

        total_rev = categories["repair"]["revenue"] + categories["cosmetics"]["revenue"]
        total_cost = categories["repair"]["cost"] + categories["cosmetics"]["cost"]
        total = {
            "revenue": total_rev, "cost": total_cost, "margin": total_rev - total_cost,
            "margin_pct": round((total_rev - total_cost) / total_rev * 100, 1) if total_rev else 0.0,
        }

        by_employee = []
        for entry in by_emp.values():
            rev = entry["repair_revenue"] + entry["cosmetics_revenue"]
            cost = entry["repair_cost"] + entry["cosmetics_cost"]
            by_employee.append({
                **entry,
                "revenue": rev, "cost": cost, "margin": rev - cost,
                "margin_pct": round((rev - cost) / rev * 100, 1) if rev else 0.0,
            })
        by_employee.sort(key=lambda e: e["margin"], reverse=True)

        return {
            "categories": categories,
            "total": total,
            "by_employee": by_employee,
            "unpriced_items": unpriced_items,
        }

    def get_turnaround_stats(self, date_from: date, date_to: date, salon_ids: list[str] | None = None,
                              service_search: str | None = None, categories: list[str] | None = None) -> dict:
        """Order fulfillment time (order accepted → moved to STATUS_ID=4,
        "Исполненный" per the real ORDER_STATUSES lookup table — i.e. work
        actually finished, not STATUS_ID=5 "Выданный" which is when the
        client picks it up) grouped by salon.

        Uses DOCS.DOC_DATE (order creation) vs the earliest
        DOCS_ORDER_HISTORY row for that order with STATUS_ID=4. "Late"
        compares that SAME STATUS_ID=4 timestamp against DATE_OUT (date
        promised to the client) — deliberately NOT DATE_OUT_FACT (actual
        pickup): a client picking up a ready order a few days late isn't
        the business being late, it's the client's schedule, so pickup
        timing must not count as "просрочка" here.

        Grouped by salon rather than by employee: DOCS_ORDER.CREATER_ID is
        whoever created the order at the register, not whoever did the
        work, so "per employee" here didn't actually identify a
        responsible party — salon attribution reuses the same mechanism as
        get_department_comparison (order-code suffix resolved via
        SalonRepository), and `salon_ids` is a plain post-filter on the
        output for the same reason documented there.

        `service_search` restricts to orders containing at least one
        service (DOC_ORDER_SERVICES) or goods (DOC_ORDER_LINES) line whose
        name contains this substring — e.g. "набойки" isolates turnaround
        for heel-tap repairs specifically instead of every order type.

        `categories` restricts to orders touching at least one of those
        categories (see _category_exists_sql) — coarser than the exact
        per-category revenue split get_daily_sales does, since this only
        needs a yes/no per order, not a revenue amount.
        """
        from app.data.salon_repository import get_salon_repository

        UNALLOC_ID = "unallocated"
        UNALLOC_NAME = "Не определено"

        empty = {"total": {"avg_days": 0.0, "late_rate": 0.0, "order_count": 0}, "by_salon": []}
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty turnaround stats")
            return empty

        # Phase 1: orders in range (cheap — DOCS.DOC_DATE is the selective
        # filter). Deliberately does NOT join DOCS_ORDER_HISTORY here.
        sql = """
            SELECT
                docs_order.id, docs.doc_num, docs.doc_date, docs_order.date_out
            FROM docs_order
                INNER JOIN docs ON (docs.doc_id = docs_order.doc_id)
            WHERE
                docs.doc_date >= ? AND docs.doc_date <= ?
        """
        params: list = [date_from, date_to]
        if service_search:
            sql += """
                AND (
                    EXISTS (
                        SELECT 1 FROM doc_order_services dos
                            INNER JOIN tovars_tbl t ON t.tovar_id = dos.tovar_id
                        WHERE dos.doc_order_id = docs_order.id AND UPPER(t.name) LIKE UPPER(?)
                    )
                    OR EXISTS (
                        SELECT 1 FROM doc_order_lines dol
                            INNER JOIN tovars_tbl t2 ON t2.tovar_id = dol.tovar_id
                        WHERE dol.doc_order_id = docs_order.id AND UPPER(t2.name) LIKE UPPER(?)
                    )
                )
            """
            needle = f"%{service_search}%"
            params += [needle, needle]

        if categories:
            cat_sql, cat_params = _category_exists_sql(set(categories))
            if cat_sql:
                sql += f" AND {cat_sql}"
                params += list(cat_params)

        # Phase 2: earliest STATUS_ID=4 ("Исполненный") history row per
        # order, batched against just this range's order ids instead of
        # aggregating the whole (multi-million-row) history table — the
        # latter measured as effectively hanging (>2min, killed) since
        # DOCS_ORDER_HISTORY has no per-row date filter cheap enough to
        # apply before the GROUP BY. Same batching technique as
        # _fetch_batched's other callers (e.g. _product_revenue_rows).
        sql_h4 = """
            SELECT doc_order_id, MIN(dt) AS mn
            FROM docs_order_history
            WHERE status_id = 4 AND doc_order_id IN ({ph})
            GROUP BY doc_order_id
        """

        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql, params)
                order_rows = cur.fetchall()
                order_ids = [r[0] for r in order_rows]
                h4_map = {oid: mn for oid, mn in _fetch_batched(cur, sql_h4, order_ids, batch=1000)}
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching turnaround stats: {e}")
            return empty

        # SalonRepository.get_by_order_code() re-reads salons.json on every
        # call by design — fine occasionally, but dominates runtime over
        # thousands of rows, so load once and suppress the reload (same
        # technique as get_department_comparison).
        repo = get_salon_repository()
        repo._load()
        original_load = repo._load
        repo._load = lambda: None
        try:
            by_salon: dict[str, dict] = {}
            for order_id, doc_num, doc_date, date_out in order_rows:
                h4_dt = h4_map.get(order_id)
                if h4_dt is None:
                    continue  # never reached "Исполненный" — excluded, same as before
                days = (h4_dt - datetime.combine(doc_date, datetime.min.time())).total_seconds() / 86400.0
                is_late = 1 if (date_out and date_out > datetime(2000, 1, 1) and h4_dt > date_out) else 0

                code = _order_salon_code(doc_num)
                salon = repo.get_by_order_code(code, doc_date.year, doc_date.month) if code else None
                salon_id = salon.id if salon else UNALLOC_ID
                salon_name = salon.name if salon else UNALLOC_NAME
                entry = by_salon.setdefault(salon_id, {
                    "salon_id": salon_id, "salon_name": salon_name,
                    "days_sum": 0.0, "order_count": 0, "late_count": 0,
                })
                entry["days_sum"] += days
                entry["order_count"] += 1
                entry["late_count"] += is_late
        finally:
            repo._load = original_load

        salon_filter = set(salon_ids) if salon_ids else None
        by_salon_list = []
        total_orders = 0
        total_late = 0
        total_days_weighted = 0.0
        for entry in by_salon.values():
            if salon_filter is not None and entry["salon_id"] not in salon_filter:
                continue
            order_count = entry["order_count"]
            avg_days = entry["days_sum"] / order_count if order_count else 0.0
            late_count = entry["late_count"]
            by_salon_list.append({
                "salon_id": entry["salon_id"],
                "salon_name": entry["salon_name"],
                "avg_days": round(avg_days, 1),
                "order_count": order_count,
                "late_count": late_count,
                "late_rate": round(late_count / order_count * 100, 1) if order_count else 0.0,
            })
            total_orders += order_count
            total_late += late_count
            total_days_weighted += avg_days * order_count

        by_salon_list.sort(key=lambda e: e["avg_days"], reverse=True)

        return {
            "total": {
                "avg_days": round(total_days_weighted / total_orders, 1) if total_orders else 0.0,
                "late_rate": round(total_late / total_orders * 100, 1) if total_orders else 0.0,
                "order_count": total_orders,
            },
            "by_salon": by_salon_list,
        }

    def get_receivables(self, date_from: date, date_to: date) -> dict:
        """Unpaid/partially-paid orders created in a date range (дебиторка).

        Filters on (DOCS_ORDER.KREDIT - DEBET) > 0 — the actual outstanding
        balance — rather than trusting PAY_STATUS_ID alone: sampled orders
        marked "Оплачен полностью" (status 3) with a positive kredit-debet
        gap exist, so the status flag can lag the real balance.
        """
        empty = {"total_count": 0, "total_amount": 0.0, "orders": []}
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty receivables")
            return empty

        sql = """
            SELECT
                d.doc_num, d.doc_date, do.id, do.pay_status_id,
                do.kredit, do.debet, c.name, c.teleph_cell
            FROM docs_order do
                INNER JOIN docs d ON (d.doc_id = do.doc_id)
                LEFT JOIN contragents c ON (c.contr_id = d.contragent_id)
            WHERE
                d.doc_date >= ? AND d.doc_date <= ?
                AND (do.kredit - do.debet) > 0
            ORDER BY d.doc_date ASC
        """

        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql, (date_from, date_to))
                rows = cur.fetchall()
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching receivables: {e}")
            return empty

        today = date.today()
        orders = []
        total_amount = 0.0
        for doc_num, doc_date, order_id, pay_status_id, kredit, debet, name, phone in rows:
            expected_amount = float(kredit or 0)
            paid_amount = float(debet or 0)
            amount = expected_amount - paid_amount
            total_amount += amount
            orders.append({
                "doc_num": str(doc_num),
                "date": doc_date.isoformat() if hasattr(doc_date, "isoformat") else str(doc_date),
                "order_id": order_id,
                "pay_status_id": pay_status_id,
                "amount": round(amount, 2),
                # Raw kredit/debet — the "discrepancy" status (3) means
                # Agbis's own status flag says "paid in full" while these
                # two disagree; showing both lets the reader see the gap
                # instead of just a vague "расхождение" label.
                "expected_amount": round(expected_amount, 2),
                "paid_amount": round(paid_amount, 2),
                "client_name": (name or "").strip() or None,
                "client_phone": (phone or "").strip() or None,
                "days_overdue": (today - doc_date).days if hasattr(doc_date, "isoformat") else None,
            })

        return {
            "total_count": len(orders),
            "total_amount": round(total_amount, 2),
            "orders": orders,
        }

    def get_unclaimed_orders(self, days: int = 90) -> dict:
        """Orders whose promised pickup date (DATE_OUT) has passed with no
        actual pickup (DATE_OUT_FACT still null) — items sitting unclaimed.

        `days` bounds how far back to look by DATE_OUT (not DOC_DATE): the
        full unbounded history goes back to 2013 (~9,200 orders), mostly
        long-dead and unactionable, so this defaults to a recent window
        that's actually worth calling clients about. "Розница <салон>"
        walk-in accounts are excluded — see search_clients docstring.
        """
        empty = {"total_count": 0, "total_amount": 0.0, "orders": []}
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty unclaimed orders")
            return empty

        # `days` is an internally-bounded int (FastAPI Query ge/le), not
        # user-supplied text — inlined because fdb can't bind CURRENT_DATE
        # - ? with an int parameter ("datetime.datetime or datetime.date
        # expected"), only a literal.
        sql = f"""
            SELECT
                d.doc_num, d.doc_date, do.date_out, do.kredit, c.name, c.teleph_cell
            FROM docs_order do
                INNER JOIN docs d ON (d.doc_id = do.doc_id)
                LEFT JOIN contragents c ON (c.contr_id = d.contragent_id)
            WHERE
                do.date_out > CURRENT_DATE - {int(days)}
                AND do.date_out < CURRENT_DATE
                AND do.date_out_fact IS NULL
                AND do.returned = 0
                AND (c.name IS NULL OR UPPER(c.name) NOT STARTING WITH 'РОЗНИЦА')
            ORDER BY do.date_out ASC
        """

        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql)
                rows = cur.fetchall()
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching unclaimed orders: {e}")
            return empty

        today = date.today()
        orders = []
        total_amount = 0.0
        for doc_num, doc_date, date_out, kredit, name, phone in rows:
            amount = float(kredit or 0)
            total_amount += amount
            due_date = date_out.date() if hasattr(date_out, "date") else date_out
            orders.append({
                "doc_num": str(doc_num),
                "order_date": doc_date.isoformat() if hasattr(doc_date, "isoformat") else str(doc_date),
                "due_date": due_date.isoformat() if hasattr(due_date, "isoformat") else str(due_date),
                "amount": round(amount, 2),
                "client_name": (name or "").strip() or None,
                "client_phone": (phone or "").strip() or None,
                "days_overdue": (today - due_date).days if due_date else None,
            })

        return {
            "total_count": len(orders),
            "total_amount": round(total_amount, 2),
            "orders": orders,
        }

    def get_returns_summary(self, date_from: date, date_to: date, salon_ids: list[str] | None = None,
                             categories: list[str] | None = None) -> dict:
        """Returned-order counts/amounts by employee for a date range (DOCS_ORDER.RETURNED=1).

        Read-only report — deliberately not wired into payroll bonuses/
        penalties. Whether a return should cost an employee money is a
        case-by-case call for a human, not something to automate from a
        raw RETURNED flag.

        `salon_ids` restricts to orders resolved to one of those salons —
        see get_daily_sales for the attribution rule and its caveats.

        `categories` restricts both the return count AND the order-count
        denominator to orders touching those categories (see
        _category_exists_sql) — so return_rate stays a rate over the same
        population, not returns-of-X over all orders.
        """
        empty = {"total": {"return_count": 0, "return_amount": 0.0, "order_count": 0, "return_rate": 0.0}, "by_employee": []}
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty returns summary")
            return empty
        salon_filter = set(salon_ids) if salon_ids else None

        cat_sql, cat_params = _category_exists_sql(set(categories)) if categories else ("", ())
        cat_clause = f" AND {cat_sql}" if cat_sql else ""

        sql_returns = f"""
            SELECT users.description, docs.doc_num, docs.doc_date, docs_order.kredit
            FROM docs_order
                INNER JOIN docs ON (docs.doc_id = docs_order.doc_id)
                INNER JOIN users ON (users.user_id = docs_order.creater_id)
            WHERE
                docs.doc_date >= ? AND docs.doc_date <= ?
                AND docs_order.returned = 1
                {cat_clause}
        """
        sql_totals = f"""
            SELECT users.description, docs.doc_num, docs.doc_date
            FROM docs_order
                INNER JOIN docs ON (docs.doc_id = docs_order.doc_id)
                INNER JOIN users ON (users.user_id = docs_order.creater_id)
            WHERE docs.doc_date >= ? AND docs.doc_date <= ?
                {cat_clause}
        """

        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql_returns, (date_from, date_to, *cat_params))
                return_rows = cur.fetchall()
                cur.execute(sql_totals, (date_from, date_to, *cat_params))
                total_rows = cur.fetchall()
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching returns summary: {e}")
            return empty

        with _SalonResolver() as resolve_salon:
            def _in_filter(doc_num, doc_date) -> bool:
                return salon_filter is None or resolve_salon(doc_num, doc_date) in salon_filter

            order_counts: dict[str, int] = {}
            for desc, doc_num, doc_date in total_rows:
                if not _in_filter(doc_num, doc_date):
                    continue
                code = _code_from_description(desc)
                if code:
                    order_counts[code] = order_counts.get(code, 0) + 1

            by_employee = []
            total_returns = 0
            total_amount = 0.0
            returns_by_code: dict[str, dict] = {}
            for desc, doc_num, doc_date, ret_amt in return_rows:
                if not _in_filter(doc_num, doc_date):
                    continue
                code = _code_from_description(desc)
                if not code:
                    continue
                entry = returns_by_code.setdefault(code, {"return_count": 0, "return_amount": 0.0})
                entry["return_count"] += 1
                entry["return_amount"] += float(ret_amt or 0)

        for code, entry in returns_by_code.items():
            order_count = order_counts.get(code, 0)
            by_employee.append({
                "code": code,
                "return_count": entry["return_count"],
                "return_amount": round(entry["return_amount"], 2),
                "order_count": order_count,
                "return_rate": round(entry["return_count"] / order_count * 100, 1) if order_count else 0.0,
            })
            total_returns += entry["return_count"]
            total_amount += entry["return_amount"]

        by_employee.sort(key=lambda e: e["return_count"], reverse=True)
        total_orders = sum(order_counts.values())

        return {
            "total": {
                "return_count": total_returns,
                "return_amount": round(total_amount, 2),
                "order_count": total_orders,
                "return_rate": round(total_returns / total_orders * 100, 1) if total_orders else 0.0,
            },
            "by_employee": by_employee,
        }

    def _product_revenue_rows(self, date_from: date, date_to: date,
                               salon_ids: list[str] | None = None,
                               categories: set[str] | None = None,
                               employee_codes: list[str] | None = None) -> dict[int, dict]:
        """Per-TOVAR_ID revenue/qty for a date range — the data behind an
        ABC-analysis, so it covers both repair services (DOC_ORDER_SERVICES)
        and cosmetics/goods (DOC_ORDER_LINES): ABC-analysis is just as
        applicable to a service lineup as to a goods lineup. `categories`
        (subset of {"repair", "cosmetics"}; None/empty = both) controls
        which of those two get queried — this is what the page's
        "Категории" filter drives for this tab. Shoes are excluded
        regardless of `categories` — SHOES_CODES are line items within a
        paired commission structure (see _parse_shoe_pairs), not
        standalone SKUs a per-item ranking would mean anything for.

        `salon_ids` restricts to orders resolved to one of those salons —
        see get_daily_sales for the attribution rule and its caveats.
        `employee_codes` restricts to orders created by those employees,
        same convention. Unlike the by-employee reports, this one does NOT
        add doc_num to the GROUP BY to support that: doing so once measured
        26-55s (vs <2s) because a per-SKU aggregate that's normally a few
        hundred rows exploded into one row per (SKU, order) — tens of
        thousands of rows — even with no filter applied. Instead, when
        either filter is active, a cheap separate pass resolves which
        DOC_NUMs qualify and the normal tight per-SKU query is restricted
        to just those via a batched IN-list (same technique as the cost
        lookup in get_margin_summary).
        """
        want_repair = not categories or 'repair' in categories
        want_cosmetics = not categories or 'cosmetics' in categories
        repair_folders = ','.join(str(x) for x in REPAIR_FOLDER_IDS)
        cosmetics_folders = ','.join(str(x) for x in COSMETICS_FOLDER_IDS)
        salon_filter = set(salon_ids) if salon_ids else None
        emp_filter = set(employee_codes) if employee_codes else None

        con = _connect()
        try:
            cur = con.cursor()

            doc_num_allowlist: list[str] | None = None
            if salon_filter is not None or emp_filter is not None:
                cur.execute(
                    "SELECT DISTINCT docs.doc_num, docs.doc_date, users.description FROM docs"
                    " INNER JOIN docs_order ON (docs_order.doc_id = docs.doc_id)"
                    " INNER JOIN users ON (users.user_id = docs_order.creater_id)"
                    " WHERE docs.doc_date >= ? AND docs.doc_date <= ?",
                    (date_from, date_to),
                )
                order_rows = cur.fetchall()
                doc_num_allowlist = []
                with _SalonResolver() as resolve_salon:
                    for doc_num, doc_date, desc in order_rows:
                        if salon_filter is not None and resolve_salon(doc_num, doc_date) not in salon_filter:
                            continue
                        if emp_filter is not None and _code_from_description(desc) not in emp_filter:
                            continue
                        doc_num_allowlist.append(str(doc_num))
                if not doc_num_allowlist:
                    return {}

            rows: list = []
            if doc_num_allowlist is None:
                if want_repair:
                    sql_repair = f"""
                        SELECT tovars_tbl.tovar_id, tovars_tbl.name, tovars_tbl.code,
                               SUM(doc_order_services.kredit), SUM(doc_order_services.qty_kredit)
                        FROM docs_order
                            INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                            INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                            INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                        WHERE docs.doc_date >= ? AND docs.doc_date <= ?
                            AND tovars_tbl.folder_id IN ({repair_folders})
                        GROUP BY tovars_tbl.tovar_id, tovars_tbl.name, tovars_tbl.code
                    """
                    cur.execute(sql_repair, (date_from, date_to))
                    rows += cur.fetchall()
                if want_cosmetics:
                    # No status_id filter — see get_daily_sales' sql_cosmetics comment.
                    sql_cosmetics = f"""
                        SELECT tovars_tbl.tovar_id, tovars_tbl.name, tovars_tbl.code,
                               SUM(doc_order_lines.kredit), SUM(doc_order_lines.qty_kredit)
                        FROM doc_order_lines
                            INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                            INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                            INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
                        WHERE docs.doc_date >= ? AND docs.doc_date <= ?
                            AND tovars_tbl.folder_id IN ({cosmetics_folders})
                        GROUP BY tovars_tbl.tovar_id, tovars_tbl.name, tovars_tbl.code
                    """
                    cur.execute(sql_cosmetics, (date_from, date_to))
                    rows += cur.fetchall()
            else:
                if want_repair:
                    sql_repair_tpl = f"""
                        SELECT tovars_tbl.tovar_id, tovars_tbl.name, tovars_tbl.code,
                               SUM(doc_order_services.kredit), SUM(doc_order_services.qty_kredit)
                        FROM docs_order
                            INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                            INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                            INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                        WHERE docs.doc_num IN ({{ph}})
                            AND docs.doc_date >= ? AND docs.doc_date <= ?
                            AND tovars_tbl.folder_id IN ({repair_folders})
                        GROUP BY tovars_tbl.tovar_id, tovars_tbl.name, tovars_tbl.code
                    """
                    rows += _fetch_batched(cur, sql_repair_tpl, doc_num_allowlist, (date_from, date_to), batch=200)
                if want_cosmetics:
                    # No status_id filter — see get_daily_sales' sql_cosmetics comment.
                    sql_cosmetics_tpl = f"""
                        SELECT tovars_tbl.tovar_id, tovars_tbl.name, tovars_tbl.code,
                               SUM(doc_order_lines.kredit), SUM(doc_order_lines.qty_kredit)
                        FROM doc_order_lines
                            INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                            INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                            INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
                        WHERE docs.doc_num IN ({{ph}})
                            AND docs.doc_date >= ? AND docs.doc_date <= ?
                            AND tovars_tbl.folder_id IN ({cosmetics_folders})
                        GROUP BY tovars_tbl.tovar_id, tovars_tbl.name, tovars_tbl.code
                    """
                    rows += _fetch_batched(cur, sql_cosmetics_tpl, doc_num_allowlist, (date_from, date_to), batch=200)
        finally:
            con.close()

        products: dict[int, dict] = {}
        for tovar_id, name, code, revenue, qty in rows:
            p = products.setdefault(tovar_id, {
                "tovar_id": tovar_id, "name": (name or "").strip(), "code": (code or "").strip(),
                "revenue": 0.0, "qty": 0.0,
            })
            p["revenue"] += float(revenue or 0)
            p["qty"] += float(qty or 0)
        return products

    def get_top_products(self, date_from: date, date_to: date, limit: int = 20,
                          salon_ids: list[str] | None = None,
                          categories: list[str] | None = None,
                          employee_codes: list[str] | None = None) -> dict:
        """Top/bottom-selling SKUs and biggest risers/fallers vs the
        preceding period of equal length, plus dead stock (see
        get_dead_stock — it's cosmetics-only regardless of `categories`
        since repair has no physical warehouse stock to go dead).

        `categories` (subset of "repair"/"cosmetics") is this tab's ABC
        analysis scope — see _product_revenue_rows. `employee_codes`
        restricts to orders created by those employees, same convention
        used everywhere else revenue is per-employee.
        """
        empty = {"top": [], "bottom": [], "rising": [], "falling": [], "dead_stock": []}
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty top products")
            return empty
        category_set = set(categories) if categories else None

        try:
            current = self._product_revenue_rows(date_from, date_to, salon_ids, category_set, employee_codes)
            span = (date_to - date_from).days + 1
            prev_to = date_from - timedelta(days=1)
            prev_from = prev_to - timedelta(days=span - 1)
            previous = self._product_revenue_rows(prev_from, prev_to, salon_ids, category_set, employee_codes)
        except Exception as e:
            logger.error(f"Error fetching top products: {e}")
            return empty

        MIN_VOLUME = 1000.0  # ignore trivial amounts when ranking % swings — a
        # SKU going from 10₽ to 100₽ is a meaningless "900% rise"

        # Union of both periods' keys, not just current's — a SKU with
        # revenue in `previous` but none in `current` (stopped selling
        # entirely) must still surface as a -100% "falling" entry instead
        # of silently vanishing from the report just because it has no row
        # in the current period.
        merged = []
        for tovar_id in set(current) | set(previous):
            cur = current.get(tovar_id)
            prev = previous.get(tovar_id)
            meta = cur or prev
            revenue = cur["revenue"] if cur else 0.0
            qty = cur["qty"] if cur else 0.0
            prev_revenue = prev["revenue"] if prev else 0.0
            is_new = revenue > 0 and not prev_revenue
            pct_change = (
                round((revenue - prev_revenue) / prev_revenue * 100, 1)
                if prev_revenue else None  # no baseline — flagged via is_new instead
            )
            merged.append({
                "tovar_id": tovar_id, "name": meta["name"], "code": meta["code"],
                "revenue": round(revenue, 2), "qty": round(qty, 1),
                "prev_revenue": round(prev_revenue, 2), "pct_change": pct_change,
                "is_new": is_new,
            })

        top = sorted((p for p in merged if p["revenue"] > 0), key=lambda p: p["revenue"], reverse=True)[:limit]
        bottom = sorted((p for p in merged if p["revenue"] > 0), key=lambda p: p["revenue"])[:limit]

        # New/reactivated SKUs (no prior-period baseline) have no defined
        # % change but are definitionally the biggest possible risers —
        # they lead the list, ranked by revenue, ahead of the numeric swings.
        new_entrants = sorted(
            (p for p in merged if p["is_new"] and p["revenue"] >= MIN_VOLUME),
            key=lambda p: p["revenue"], reverse=True,
        )
        swinging = [p for p in merged if p["pct_change"] is not None and max(p["revenue"], p["prev_revenue"]) >= MIN_VOLUME]
        rising = (new_entrants + sorted(swinging, key=lambda p: p["pct_change"], reverse=True))[:limit]
        falling = sorted(swinging, key=lambda p: p["pct_change"])[:limit]

        try:
            dead_stock = (
                self.get_dead_stock(date_from, date_to, limit=limit * 3)
                if category_set is None or 'cosmetics' in category_set
                else []
            )
        except Exception as e:
            logger.error(f"Error fetching dead stock: {e}")
            dead_stock = []

        return {"top": top, "bottom": bottom, "rising": rising, "falling": falling, "dead_stock": dead_stock}

    def get_dead_stock(self, date_from: date, date_to: date, limit: int = 50) -> list[dict]:
        """Cosmetics SKUs that are physically in stock (positive warehouse
        remainder, computed as SUM(QTY_DEBET - QTY_KREDIT) over the whole
        receipt/write-off ledger, not just this period) but had zero sales
        in the given date range — likely overstocked or dead inventory.

        Repair-folder items are excluded: they're services, not physical
        goods, so "in stock" is meaningless for them (confirmed: 0 of the
        ~2900 SKUs with positive DOC_SCLAD_LINES remainder belong to a
        repair folder). Discontinued items (IS_NOT_USED) are excluded too
        — they're already known to be out of rotation, not surprises.

        Salon filtering isn't offered here: DOC_SCLAD_LINES tracks a single
        shared warehouse ledger per SKU, not a per-order/per-salon split
        like the sales tables, so there's no way to attribute "this SKU's
        stock" to one salon the way orders attribute revenue.
        """
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty dead stock")
            return []

        cosmetics_folders = ','.join(str(x) for x in COSMETICS_FOLDER_IDS)

        sql_stock = f"""
            SELECT s.tovar_id, t.name, t.code, s.remain
            FROM (
                SELECT tovar_id, SUM(qty_debet - qty_kredit) as remain
                FROM doc_sclad_lines
                GROUP BY tovar_id
                HAVING SUM(qty_debet - qty_kredit) > 0
            ) s
            INNER JOIN tovars_tbl t ON t.tovar_id = s.tovar_id
            WHERE t.folder_id IN ({cosmetics_folders})
                AND (t.is_not_used IS NULL OR t.is_not_used = 0)
        """
        sql_sold = f"""
            SELECT DISTINCT doc_order_lines.tovar_id
            FROM doc_order_lines
                INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                INNER JOIN docs_order_history ON (docs_order.id = docs_order_history.doc_order_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
            WHERE docs_order_history.status_id = 5
                AND docs.doc_date >= ? AND docs.doc_date <= ?
                AND tovars_tbl.folder_id IN ({cosmetics_folders})
        """

        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql_stock)
                stock_rows = cur.fetchall()
                cur.execute(sql_sold, (date_from, date_to))
                sold_ids = {r[0] for r in cur.fetchall()}
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching dead stock: {e}")
            return []

        dead = [
            {"tovar_id": tovar_id, "name": (name or "").strip(), "code": (code or "").strip(),
             "stock_qty": float(remain or 0)}
            for tovar_id, name, code, remain in stock_rows
            if tovar_id not in sold_ids
        ]
        dead.sort(key=lambda p: p["stock_qty"], reverse=True)
        return dead[:limit]

    def get_workplace_summary(self, date_from: date, date_to: date, salon_ids: list[str] | None = None) -> dict:
        """Throughput (revenue + operation count) per WORK_PLACE for a date range.

        This is NOT a per-hour productivity figure — that would need
        DATE_BEG/DATE_END on USER_SESSION_ACTIONS to hold real elapsed
        work time, but on this DB they're equal (instant event stamps) for
        effectively all rows, and TECHNOLOGIST_INPUT_ID/OUTPUT_ID are null
        on every sampled row too. What *is* reliably populated is
        WORK_PLACE_ID + a link to the sold service (DOC_ORDER_SERVICES_ID),
        so this reports volume/revenue per checkpoint instead — on this
        business's data the "work places" turn out to be the repair
        intake/dispatch scan checkpoints per branch (e.g. "Ремонт ВХОД",
        "Ремонт ВЫХОД"), so this doubles as a per-branch repair-workflow
        throughput view.

        `salon_ids` restricts to orders resolved to one of those salons —
        see get_daily_sales for the attribution rule and its caveats. Note
        this is somewhat redundant with the workplace name itself (which
        already usually names the branch), but included for filter
        consistency with the rest of this page.

        Selecting per-row DOC_NUM/DOC_DATE (needed to resolve a salon)
        means this can't be aggregated in SQL — one measurement showed 27s
        for a range that returns ~50k raw USER_SESSION_ACTIONS rows, vs a
        fraction of a second when only the (much smaller) per-workplace
        aggregate is needed. So when no filter is given, skip the doc join
        entirely and let SQL aggregate by workplace directly; only pull
        (and resolve) raw per-order rows when a salon filter is active.
        """
        empty = {"total_revenue": 0.0, "total_operations": 0, "work_places": []}
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty workplace summary")
            return empty
        salon_filter = set(salon_ids) if salon_ids else None

        by_name: dict[str, dict] = {}
        try:
            con = _connect()
            try:
                cur = con.cursor()
                if salon_filter is None:
                    sql = """
                        SELECT wp.name, SUM(dos.kredit), COUNT(*)
                        FROM user_session_actions usa
                            INNER JOIN doc_order_services dos ON (dos.id = usa.doc_order_services_id)
                            INNER JOIN work_places wp ON (wp.id = usa.work_place_id)
                        WHERE usa.date_beg >= ? AND usa.date_beg <= ?
                        GROUP BY wp.name
                    """
                    cur.execute(sql, (date_from, date_to))
                    for name, revenue, op_count in cur.fetchall():
                        name = (name or "").strip()
                        entry = by_name.setdefault(name, {"name": name, "operation_count": 0, "revenue": 0.0})
                        entry["operation_count"] += op_count
                        entry["revenue"] += float(revenue or 0)
                else:
                    sql = """
                        SELECT wp.name, dos.kredit, d.doc_num, d.doc_date
                        FROM user_session_actions usa
                            INNER JOIN doc_order_services dos ON (dos.id = usa.doc_order_services_id)
                            INNER JOIN work_places wp ON (wp.id = usa.work_place_id)
                            INNER JOIN docs_order do2 ON (do2.id = dos.doc_order_id)
                            INNER JOIN docs d ON (d.doc_id = do2.doc_id)
                        WHERE usa.date_beg >= ? AND usa.date_beg <= ?
                    """
                    cur.execute(sql, (date_from, date_to))
                    rows = cur.fetchall()
                    with _SalonResolver() as resolve_salon:
                        for name, revenue, doc_num, doc_date in rows:
                            if resolve_salon(doc_num, doc_date) not in salon_filter:
                                continue
                            name = (name or "").strip()
                            entry = by_name.setdefault(name, {"name": name, "operation_count": 0, "revenue": 0.0})
                            entry["operation_count"] += 1
                            entry["revenue"] += float(revenue or 0)
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching workplace summary: {e}")
            return empty

        work_places = sorted(by_name.values(), key=lambda w: w["revenue"], reverse=True)
        for w in work_places:
            w["avg_ticket"] = round(w["revenue"] / w["operation_count"], 2) if w["operation_count"] else 0.0

        return {
            "total_revenue": round(sum(w["revenue"] for w in work_places), 2),
            "total_operations": sum(w["operation_count"] for w in work_places),
            "work_places": work_places,
        }

    def get_department_comparison(self, date_from: date, date_to: date, salon_ids: list[str] | None = None,
                                   categories: list[str] | None = None, employee_codes: list[str] | None = None) -> dict:
        """Revenue/order comparison by salon for a date range.

        Salon attribution is primarily by "Склад приёма" (reception
        warehouse, DOCS_ORDER.SCLAD_KREDIT_ID) resolved against
        Salon.sclad_ids (bound on the Salons page) — this matches the
        authoritative "Суммы заказов по приемным пунктам" report exactly,
        confirmed against a real export covering 180 days. The -N suffix
        on DOCS.DOC_NUM (same mechanism payroll_service's payroll-by-salon
        report uses, time-aware for renamed/relocated points) is only a
        fallback for the rare order whose SCLAD_KREDIT_ID is NULL/unbound.

        `salon_ids`, if given, just restricts the *output* to those salons
        — the whole point of this endpoint is grouping by salon, so
        "filtering" here is a plain post-filter, not a resolution change.

        `categories` (subset of get_daily_sales' category keys; None/empty
        = all) restricts which category's rows get counted at all, same
        semantics as the "Обзор" tab's category filter. `employee_codes`
        restricts to orders created by those employees (Обзор's exact
        attribution — see get_daily_sales), same convention this app uses
        everywhere revenue is attributed to "an employee".
        """
        from app.data.salon_repository import get_salon_repository

        UNALLOC_ID = "unallocated"
        UNALLOC_NAME = "Не определено"

        empty = {"total_revenue": 0.0, "departments": []}
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty department comparison")
            return empty

        cat_filter = set(categories) if categories else None
        want_repair = cat_filter is None or 'repair' in cat_filter
        want_cosmetics = cat_filter is None or 'cosmetics' in cat_filter
        want_shoes = cat_filter is None or 'shoes' in cat_filter
        emp_filter = set(employee_codes) if employee_codes else None

        repair_folders = ','.join(str(x) for x in REPAIR_FOLDER_IDS)
        cosmetics_folders = ','.join(str(x) for x in COSMETICS_FOLDER_IDS)
        shoes_sales_codes = tuple(c for c in SHOES_CODES if c not in ('0', '1'))
        shoes_placeholders = ','.join(['?'] * len(shoes_sales_codes))

        # users.description is only needed to support employee_codes — same
        # join get_daily_sales already uses for the same purpose.
        sql_repair = f"""
            SELECT docs.doc_num, docs.doc_date, SUM(doc_order_services.kredit), docs_order.sclad_kredit_id, users.description
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE
                docs.doc_date >= ? AND docs.doc_date <= ?
                AND tovars_tbl.folder_id IN ({repair_folders})
            GROUP BY docs.doc_num, docs.doc_date, docs_order.sclad_kredit_id, users.description
        """
        # No status_id filter — see get_daily_sales' sql_cosmetics comment.
        sql_cosmetics = f"""
            SELECT docs.doc_num, docs.doc_date, SUM(doc_order_lines.kredit), docs_order.sclad_kredit_id, users.description
            FROM doc_order_lines
                INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE
                docs.doc_date >= ? AND docs.doc_date <= ?
                AND tovars_tbl.folder_id IN ({cosmetics_folders})
            GROUP BY docs.doc_num, docs.doc_date, docs_order.sclad_kredit_id, users.description
        """
        sql_shoes = f"""
            SELECT docs.doc_num, docs.doc_date, SUM(doc_order_services.kredit), docs_order.sclad_kredit_id, users.description
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE
                docs.doc_date >= ? AND docs.doc_date <= ?
                AND tovars_tbl.code IN ({shoes_placeholders})
            GROUP BY docs.doc_num, docs.doc_date, docs_order.sclad_kredit_id, users.description
        """

        try:
            con = _connect()
            try:
                cur = con.cursor()
                rows = []
                if want_repair:
                    cur.execute(sql_repair, (date_from, date_to))
                    rows += cur.fetchall()
                if want_cosmetics:
                    cur.execute(sql_cosmetics, (date_from, date_to))
                    rows += cur.fetchall()
                if want_shoes:
                    cur.execute(sql_shoes, (date_from, date_to, *shoes_sales_codes))
                    rows += cur.fetchall()
                # Same previously-uncounted revenue get_daily_sales now
                # covers (certificates, keys, custom leather goods, etc.) —
                # no per-category breakdown needed here, just folded into
                # each salon's total like everything else, unless a
                # category filter narrows it down.
                rows += [
                    (doc_num, doc_date, kredit, sclad_id, desc)
                    for doc_date, desc, doc_num, category, kredit, sclad_id in self._extra_category_rows(cur, date_from, date_to)
                    if cat_filter is None or category in cat_filter
                ]
                sclad_names = self._sclad_names(cur)
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching department comparison: {e}")
            return empty

        # SalonRepository.get_by_order_code() re-reads salons.json from disk
        # on every call (by design, for the two-process HR/payroll setup) —
        # fine for occasional lookups, but for thousands of order rows here
        # it dominates runtime, so load once and suppress the reload for
        # the duration of this loop.
        repo = get_salon_repository()
        repo._load()
        original_load = repo._load
        repo._load = lambda: None
        try:
            totals: dict[str, dict] = {}
            for doc_num, doc_date, revenue, sclad_id, desc in rows:
                if emp_filter is not None and _code_from_description(desc) not in emp_filter:
                    continue
                # Primary: "Склад приёма" (reception warehouse,
                # DOCS_ORDER.SCLAD_KREDIT_ID) — matches the authoritative
                # "Суммы заказов по приемным пунктам" report exactly (spot
                # checked against a real export: every one of the 7
                # physical salons matched to the RUB either exactly or
                # within a handful of RUB on all but 2 dates out of 180).
                # Bound via the Salons page (Salon.sclad_ids); falls back
                # to the raw Agbis SCLAD name if no salon claims it.
                salon = repo.get_by_sclad_id(sclad_id, doc_date.year, doc_date.month) if sclad_id is not None else None
                if salon:
                    salon_id, salon_name = salon.id, salon.name
                elif sclad_id is not None and sclad_id in sclad_names:
                    salon_id, salon_name = f"sclad:{sclad_id}", sclad_names[sclad_id]
                else:
                    # SCLAD_KREDIT_ID itself is NULL/unresolvable (rare) —
                    # fall back to the doc_num suffix, the older mechanism.
                    code = _order_salon_code(doc_num)
                    fallback_salon = repo.get_by_order_code(code, doc_date.year, doc_date.month) if code else None
                    if fallback_salon:
                        salon_id, salon_name = fallback_salon.id, fallback_salon.name
                    else:
                        salon_id, salon_name = UNALLOC_ID, UNALLOC_NAME
                entry = totals.setdefault(salon_id, {
                    "salon_id": salon_id, "salon_name": salon_name,
                    "revenue": 0.0, "doc_nums": set(),
                })
                entry["revenue"] += float(revenue or 0)
                entry["doc_nums"].add(str(doc_num))
        finally:
            repo._load = original_load

        salon_filter = set(salon_ids) if salon_ids else None
        departments = []
        for entry in totals.values():
            if salon_filter is not None and entry["salon_id"] not in salon_filter:
                continue
            order_count = len(entry["doc_nums"])
            departments.append({
                "salon_id": entry["salon_id"],
                "salon_name": entry["salon_name"],
                "revenue": round(entry["revenue"], 2),
                "order_count": order_count,
                "avg_check": round(entry["revenue"] / order_count, 2) if order_count else 0.0,
            })
        departments.sort(key=lambda d: d["revenue"], reverse=True)

        return {
            "total_revenue": round(sum(d["revenue"] for d in departments), 2),
            "departments": departments,
        }

    def get_cash_moves(self, date_from: date | None = None, date_to: date | None = None) -> list[dict]:
        """Load cash movements from DOC_KASSA_MOVES.

        Also resolves KASSA_KREDIT/KASSA_DEBET (the actual source/
        destination register — confirmed against real "Выравнивание
        кассы"/"Возврат инкасации" rows: KASSA_KREDIT=54 "Основная",
        KASSA_DEBET=a salon's register) with their KASSES.name. DEP_SRC_ID
        is a *different*, admin-assigned id space (see
        CashConfigRepository/DEFAULT_BRANCHES) that tracks which
        department filed the document — for a normal инкассация out of a
        salon it happens to match that salon's register, but for a
        reverse transfer (Основная → salon, e.g. to top up/balance a
        till) it does not reliably identify either side of the move, so
        filtering by DEP_SRC_ID alone silently misses those — callers
        that need "did this move touch register X" should match against
        KASSA_KREDIT/KASSA_DEBET instead.
        """
        if not FIREBIRD_AVAILABLE:
            return []
        conditions = ["dkm.DK_DATE > DATE '2023-12-31'"]
        params: list = []
        if date_from:
            conditions.append("dkm.DK_DATE >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("dkm.DK_DATE <= ?")
            params.append(date_to)
        where = " AND ".join(conditions)
        sql = f"""
            SELECT dkm.ID_KASSES_MOVE, dkm.DK_DATE, dkm.SUMM, dkm.BASIS, dkm.OWN_USR_ID, dkm.DEP_SRC_ID,
                   dkm.KASSA_KREDIT, k1.name AS KASSA_KREDIT_NAME,
                   dkm.KASSA_DEBET, k2.name AS KASSA_DEBET_NAME
            FROM DOC_KASSA_MOVES dkm
                LEFT JOIN KASSES k1 ON k1.id = dkm.KASSA_KREDIT
                LEFT JOIN KASSES k2 ON k2.id = dkm.KASSA_DEBET
            WHERE {where}
            ORDER BY dkm.DK_DATE DESC
        """
        try:
            conn = _connect()
            cur = conn.cursor()
            cur.execute(sql, params)
            cols = [c[0] for c in cur.description]
            rows = []
            for r in cur.fetchall():
                row = dict(zip(cols, r))
                if isinstance(row.get("DK_DATE"), date):
                    row["DK_DATE"] = row["DK_DATE"].isoformat()
                row["KASSA_KREDIT_NAME"] = _kassa_display_name(row.get("KASSA_KREDIT"), row.get("KASSA_KREDIT_NAME"))
                row["KASSA_DEBET_NAME"] = _kassa_display_name(row.get("KASSA_DEBET"), row.get("KASSA_DEBET_NAME"))
                rows.append(row)
            conn.close()
            return rows
        except Exception as e:
            logger.warning(f"get_cash_moves error: {e}")
            return []

    def get_cash_balances(self) -> list[dict]:
        """Current cash-on-hand per register (KASSA), computed from
        DOCS_KASSA — the full cash ledger (sales, refunds, prepayments,
        salary payouts, инкассация, ...), unlike DOC_KASSA_MOVES above
        which only covers transfers between registers. DEBET increases a
        register's cash, KREDIT decreases it (confirmed against real
        rows: "Реализация" sales post to DEBET, "Инкассация" posts KREDIT
        at the source register and a matching DEBET at the receiving one)
        — so balance = SUM(DEBET) - SUM(KREDIT), all-time (there's no
        periodic "opening balance" reset row in this data; it's one
        running total since 2013).

        Deliberately skips the DOCS join for the date: this is "balance
        right now", which needs every historical row regardless of date,
        and DOCS_KASSA/KASSES alone answers that in <1s — adding DOCS to
        get DOC_DATE (unneeded here) was measured at ~14s for the same
        aggregate over ~290k rows.

        "Основная" (id 54) is the central register that everything gets
        инкассация'd into — its balance is a 13-year cumulative total,
        not physical cash sitting in a drawer, so don't read it the same
        way as a branch's till float. KASSES has ~19 rows total (legacy/
        test/franchise registers included), but only the working salon
        registers are worth surfacing here — filtered down to CASH_BALANCE_
        KASSA_IDS (with a display-name override for the one KASSES.NAME is
        stale on: id 21066 is still labeled "5_Пассаж" in Agbis after that
        location was renamed to Гранд Палас).
        """
        if not FIREBIRD_AVAILABLE:
            return []
        sql = f"""
            SELECT dk.kassa_id, k.name, SUM(dk.debet - dk.kredit) as balance
            FROM docs_kassa dk
                INNER JOIN kasses k ON k.id = dk.kassa_id
            WHERE dk.kassa_id IN ({','.join(str(x) for x in CASH_BALANCE_KASSA_IDS)})
            GROUP BY dk.kassa_id, k.name
            ORDER BY balance DESC
        """
        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql)
                rows = cur.fetchall()
            finally:
                con.close()
        except Exception as e:
            logger.warning(f"get_cash_balances error: {e}")
            return []
        return [
            {
                "kassa_id": kassa_id,
                "name": CASH_BALANCE_NAME_OVERRIDES.get(kassa_id, (name or "").strip()),
                "balance": round(float(balance or 0), 2),
            }
            for kassa_id, name, balance in rows
        ]

    def get_daily_cash_balances(
        self,
        kassa_id: int,
        date_from: date,
        date_to: date,
    ) -> dict:
        """Opening/closing cash balance per day for one register — the
        report employees reconcile their physical cash count against.

        Same ledger and same sign convention as get_cash_balances
        (DEBET increases the register, KREDIT decreases it), just cut by
        date instead of all-time, so:

            opening(D) = SUM(debet - kredit) over every row dated < D
            closing(D) = opening(D) + приход - расход - инкассация

        There is no "opening balance" row in this data to read the first
        figure off of — the running total starts in 2013 and never
        resets — so the opening balance is genuinely the sum of all
        history before the day, which is why this needs a separate
        baseline query rather than just aggregating the visible range.

        DOCS_KASSA has no date column of its own; the date lives on the
        parent document (DOC_ID → DOCS.DOC_DATE), hence the join
        get_cash_balances deliberately avoids. That join is cheap here
        (~0.1s measured) precisely because this is scoped to one
        kassa_id — the ~14s figure in get_cash_balances is for the
        unfiltered aggregate across every register, so don't "optimize"
        this by dropping the join: without it the day boundaries, which
        are the entire point of this report, don't exist.

        Инкассация is reported net (KREDIT - DEBET) in its own column
        rather than folded into приход/расход: a register can also be
        *topped up* from the central "Основная" register under that same
        basis (7 such rows in 2026, all "Приход с кассы: Основная"), and
        counting those as приход would overstate a salon's takings by
        money it never earned. A negative Инкассация is that top-up.

        Days with no documents are returned too, as flat rows where
        closing == opening. That is deliberate: a day that is missing
        from the report reads as "no data", while a day showing zero
        turnover against an unchanged balance is a positive statement
        that the ledger says nothing moved — the distinction that
        matters when reconciling a shortfall.
        """
        empty = {
            "kassa_id": kassa_id,
            "kassa_name": CASH_BALANCE_NAME_OVERRIDES.get(kassa_id),
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "clamped": False,
            "opening": 0.0,
            "closing": 0.0,
            "days": [],
            "entries": [],
        }
        if not FIREBIRD_AVAILABLE:
            return empty

        if date_to < date_from:
            date_from, date_to = date_to, date_from
        clamped = False
        span_days = (date_to - date_from).days + 1
        if span_days > DAILY_BALANCE_MAX_DAYS:
            date_from = date_to - timedelta(days=DAILY_BALANCE_MAX_DAYS - 1)
            clamped = True

        baseline_sql = """
            SELECT SUM(dk.debet - dk.kredit)
            FROM docs_kassa dk
                INNER JOIN docs d ON d.doc_id = dk.doc_id
            WHERE dk.kassa_id = ? AND d.doc_date < ?
        """
        daily_sql = f"""
            SELECT d.doc_date,
                   SUM(CASE WHEN dk.basis_id <> {KASSA_BASIS_INKASSATION} THEN dk.debet  ELSE 0 END),
                   SUM(CASE WHEN dk.basis_id <> {KASSA_BASIS_INKASSATION} THEN dk.kredit ELSE 0 END),
                   SUM(CASE WHEN dk.basis_id  = {KASSA_BASIS_INKASSATION} THEN dk.kredit - dk.debet ELSE 0 END),
                   COUNT(*)
            FROM docs_kassa dk
                INNER JOIN docs d ON d.doc_id = dk.doc_id
            WHERE dk.kassa_id = ? AND d.doc_date >= ? AND d.doc_date <= ?
            GROUP BY d.doc_date
        """
        entries_sql = """
            SELECT d.doc_date, d.doc_time, d.doc_num, d.basis, d.user_id,
                   dk.id, dk.basis_id, b.name, dk.debet, dk.kredit
            FROM docs_kassa dk
                INNER JOIN docs d ON d.doc_id = dk.doc_id
                LEFT JOIN doc_kassa_basises b ON b.id = dk.basis_id
            WHERE dk.kassa_id = ? AND d.doc_date >= ? AND d.doc_date <= ?
            ORDER BY d.doc_date, d.doc_time
        """
        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(baseline_sql, (kassa_id, date_from))
                opening = float((cur.fetchone() or [0])[0] or 0)
                cur.execute(daily_sql, (kassa_id, date_from, date_to))
                daily_rows = cur.fetchall()
                cur.execute(entries_sql, (kassa_id, date_from, date_to))
                entry_rows = cur.fetchall()
                cur.execute("SELECT name FROM kasses WHERE id = ?", (kassa_id,))
                name_row = cur.fetchone()
            finally:
                con.close()
        except Exception as e:
            logger.warning(f"get_daily_cash_balances error: {e}")
            return empty

        by_date = {
            row[0]: (float(row[1] or 0), float(row[2] or 0), float(row[3] or 0), int(row[4] or 0))
            for row in daily_rows
        }

        days = []
        running = opening
        cursor_date = date_from
        while cursor_date <= date_to:
            income, expense, collection, count = by_date.get(cursor_date, (0.0, 0.0, 0.0, 0))
            day_open = running
            running = day_open + income - expense - collection
            days.append({
                "date": cursor_date.isoformat(),
                "opening": round(day_open, 2),
                "income": round(income, 2),
                "expense": round(expense, 2),
                "collection": round(collection, 2),
                "closing": round(running, 2),
                "entry_count": count,
            })
            cursor_date += timedelta(days=1)

        entries = []
        for (doc_date, doc_time, doc_num, doc_basis, user_id,
             entry_id, basis_id, basis_name, debet, kredit) in entry_rows:
            entries.append({
                "id": entry_id,
                "date": doc_date.isoformat() if isinstance(doc_date, date) else str(doc_date or ""),
                "time": doc_time.strftime("%H:%M") if hasattr(doc_time, "strftime") else "",
                "doc_num": (doc_num or "").strip(),
                "basis_id": basis_id,
                "basis_name": (basis_name or "").strip(),
                "basis_text": (doc_basis or "").strip(),
                "debet": round(float(debet or 0), 2),
                "kredit": round(float(kredit or 0), 2),
                "user_id": str(user_id or ""),
            })

        return {
            "kassa_id": kassa_id,
            "kassa_name": _kassa_display_name(kassa_id, name_row[0] if name_row else None),
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "clamped": clamped,
            "opening": round(opening, 2),
            "closing": days[-1]["closing"] if days else round(opening, 2),
            "days": days,
            "entries": entries,
        }

    def get_cash_move_by_id(self, move_id: str) -> Optional[dict]:
        """Load a single cash movement by ID from DOC_KASSA_MOVES. See
        get_cash_moves for why KASSA_KREDIT/KASSA_DEBET (not DEP_SRC_ID)
        are the fields that reliably identify the two registers."""
        if not FIREBIRD_AVAILABLE:
            return None
        sql = """
            SELECT dkm.ID_KASSES_MOVE, dkm.DK_DATE, dkm.SUMM, dkm.BASIS, dkm.OWN_USR_ID, dkm.DEP_SRC_ID,
                   dkm.KASSA_KREDIT, k1.name AS KASSA_KREDIT_NAME,
                   dkm.KASSA_DEBET, k2.name AS KASSA_DEBET_NAME
            FROM DOC_KASSA_MOVES dkm
                LEFT JOIN KASSES k1 ON k1.id = dkm.KASSA_KREDIT
                LEFT JOIN KASSES k2 ON k2.id = dkm.KASSA_DEBET
            WHERE dkm.ID_KASSES_MOVE = ?
        """
        try:
            conn = _connect()
            cur = conn.cursor()
            cur.execute(sql, [move_id])
            cols = [c[0] for c in cur.description]
            row = cur.fetchone()
            conn.close()
            if row is None:
                return None
            result = dict(zip(cols, row))
            if isinstance(result.get("DK_DATE"), date):
                result["DK_DATE"] = result["DK_DATE"].isoformat()
            result["KASSA_KREDIT_NAME"] = _kassa_display_name(result.get("KASSA_KREDIT"), result.get("KASSA_KREDIT_NAME"))
            result["KASSA_DEBET_NAME"] = _kassa_display_name(result.get("KASSA_DEBET"), result.get("KASSA_DEBET_NAME"))
            return result
        except Exception as e:
            logger.warning(f"get_cash_move_by_id error: {e}")
            return None


    def get_agbis_users(self) -> list[dict]:
        """All USERS rows for the "Пользователи АГБИС" admin page — role
        (MST_ROLES), подразделение (DEPS) and the per-user flags Agbis
        itself exposes (курьер/инкассатор/технолог/бригадир/личный
        кабинет). USER_POSTS (должность) isn't joined: every row in this
        DB has a NULL name, so it's unused in this deployment.

        Includes USER_PASSWORD, BARCODE and INN for the user detail card —
        Agbis stores the login password in cleartext on this row (it's the
        short PIN-style code used at the POS terminal, not a hashed web
        password), so this is surfacing exactly what Agbis's own desktop
        client already shows an admin editing a user, nothing new is
        exposed. The route stays behind the existing "payroll" permission.
        """
        if not FIREBIRD_AVAILABLE:
            return []
        sql = """
            SELECT u.user_id, u.description, u.is_working, r.name, r.is_admin,
                   d.name, u.phone, u.teleph_cell, u.email, u.comment,
                   u.is_courier, u.is_inkass, u.is_technologist, u.is_brigadier,
                   u.is_cabinet_user, u.is_cabinet_admin, u.is_system,
                   u.user_password, u.barcode, u.inn
            FROM users u
                LEFT JOIN mst_roles r ON r.id = u.role_id
                LEFT JOIN deps d ON d.dep_id = u.dep_id
            ORDER BY u.is_working DESC, u.description
        """
        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql)
                rows = cur.fetchall()
            finally:
                con.close()
        except Exception as e:
            logger.warning(f"get_agbis_users error: {e}")
            return []
        return [
            {
                "user_id": user_id,
                "description": (description or "").strip(),
                "is_working": bool(is_working),
                "role_name": (role_name or "").strip() if role_name else None,
                "is_admin_role": bool(is_admin),
                "dep_name": (dep_name or "").strip() if dep_name else None,
                "phone": (phone or "").strip() or None,
                "mobile": (mobile or "").strip() or None,
                "email": (email or "").strip() or None,
                "comment": (comment or "").strip() or None,
                "is_courier": bool(is_courier),
                "is_inkass": bool(is_inkass),
                "is_technologist": bool(is_technologist),
                "is_brigadier": bool(is_brigadier),
                "is_cabinet_user": bool(is_cabinet_user),
                "is_cabinet_admin": bool(is_cabinet_admin),
                "is_system": bool(is_system),
                "password": (password or "").strip() or None,
                "barcode": (barcode or "").strip() or None,
                "inn": (inn or "").strip() or None,
            }
            for (user_id, description, is_working, role_name, is_admin, dep_name, phone, mobile,
                 email, comment, is_courier, is_inkass, is_technologist, is_brigadier,
                 is_cabinet_user, is_cabinet_admin, is_system,
                 password, barcode, inn) in rows
        ]

    def get_agbis_user_actions(self, user_id: int, day: date) -> list[dict]:
        """Per-order action log for one user on one day, translated from
        Agbis's raw DOCS_ORDER_HISTORY rows into human-readable entries —
        what kind of action it was, and (when the underlying fields
        actually changed) what changed from what to what: status, oplata,
        delivery status, deadline date, amount, discount, warehouse.

        Filters on DOH.USER_ID (the actor who made *this* history entry),
        not CREATER_ID (the order's original creator) — a user's edits on
        an order someone else created still show up, but someone else's
        edits on an order *this* user created don't, which is what "what
        did this person do" should mean. Note the free-text BASIS can
        still occasionally name a different person (observed once: an
        entry attributed to this USER_ID whose own text read "Пользователь
        внесший изменения: <other name>") — Agbis's own quirk, not
        something this query can resolve further.

        Before/after diffs come from comparing each row's field snapshot
        (STATUS_ID, PAY_STATUS_ID, DELIVERY_STATUS_ID, DATE_OUT, DEBET,
        KREDIT, DISCOUNT, CURRENT_SCLAD_ID) to the *previous* history row
        for the same DOC_ORDER_ID (by any user, not just this one) — Agbis
        itself doesn't store a diff, only point-in-time snapshots, so this
        pulls the full history of every order touched that day (usually a
        few dozen rows each) to reconstruct it locally.
        """
        if not FIREBIRD_AVAILABLE:
            return []
        next_day = day + timedelta(days=1)
        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(
                    "SELECT DISTINCT doc_order_id FROM docs_order_history WHERE user_id = ? AND dt >= ? AND dt < ?",
                    (user_id, day, next_day),
                )
                doc_order_ids = [r[0] for r in cur.fetchall()]
                if not doc_order_ids:
                    return []

                order_num_by_id: dict[int, str] = {}
                num_rows = _fetch_batched(
                    cur,
                    "SELECT do2.id, d.doc_num FROM docs_order do2 "
                    "INNER JOIN docs d ON d.doc_id = do2.doc_id WHERE do2.id IN ({ph})",
                    doc_order_ids,
                )
                order_num_by_id = {oid: (num or "").strip() for oid, num in num_rows}

                history_rows = _fetch_batched(
                    cur,
                    "SELECT doc_order_id, dt, user_id, basis, status_id, pay_status_id, "
                    "delivery_status_id, debet, kredit, discount, date_out, current_sclad_id "
                    "FROM docs_order_history WHERE doc_order_id IN ({ph}) ORDER BY doc_order_id, dt",
                    doc_order_ids,
                )

                cur.execute("SELECT id, name FROM sclads")
                sclad_names = {sid: (name or "").strip() for sid, name in cur.fetchall()}
            finally:
                con.close()
        except Exception as e:
            logger.warning(f"get_agbis_user_actions error: {e}")
            return []

        order_status = {1: "Новый", 2: "На хранении", 3: "В исполнении", 4: "Исполненный",
                         5: "Выданный", 6: "Закрытый", 7: "Отменённый"}
        pay_status = {1: "Не оплачен", 2: "Оплачен частично", 3: "Оплачен полностью"}
        delivery_status = {1: "Оформлен на курьера", 2: "Оформлен в чистомат", 3: "Принят в Чистомат",
                            4: "Принят курьером", 5: "Принят на фабрику", 6: "Ожидает согласования",
                            7: "Согласован", 8: "Не согласован", 9: "Обработан", 10: "Передан курьеру",
                            11: "Размещен в Чистомате", 12: "Выдан клиенту", 13: "Просрочен"}

        results: list[dict] = []
        prev_by_order: dict[int, tuple] = {}
        for doc_order_id, dt, row_user_id, basis, status_id, pay_status_id, \
                delivery_status_id, debet, kredit, discount, date_out, current_sclad_id in history_rows:
            prev = prev_by_order.get(doc_order_id)
            changes: list[str] = []
            sclad_changed = False
            sclad_from: str | None = None
            sclad_to: str | None = None
            if prev is not None:
                (p_status, p_pay, p_delivery, p_debet, p_kredit, p_discount, p_date_out, p_sclad) = prev
                if status_id != p_status:
                    changes.append(f"статус: {order_status.get(p_status, p_status)} → {order_status.get(status_id, status_id)}")
                if pay_status_id != p_pay:
                    changes.append(f"оплата: {pay_status.get(p_pay, p_pay)} → {pay_status.get(pay_status_id, pay_status_id)}")
                if delivery_status_id != p_delivery:
                    changes.append(f"доставка: {delivery_status.get(p_delivery, p_delivery)} → {delivery_status.get(delivery_status_id, delivery_status_id)}")
                if date_out != p_date_out and date_out is not None:
                    old_d = p_date_out.strftime('%d.%m.%Y') if p_date_out else "—"
                    changes.append(f"дата выдачи: {old_d} → {date_out.strftime('%d.%m.%Y')}")
                if debet != p_debet or kredit != p_kredit:
                    if debet != p_debet:
                        changes.append(f"сумма прихода: {p_debet or 0:.0f} ₽ → {debet or 0:.0f} ₽")
                    if kredit != p_kredit:
                        changes.append(f"сумма расхода: {p_kredit or 0:.0f} ₽ → {kredit or 0:.0f} ₽")
                if discount != p_discount and (discount or 0) != (p_discount or 0):
                    changes.append(f"скидка: {p_discount or 0}% → {discount or 0}%")
                if current_sclad_id != p_sclad:
                    sclad_changed = True
                    sclad_from = sclad_names.get(p_sclad, str(p_sclad))
                    sclad_to = sclad_names.get(current_sclad_id, str(current_sclad_id))
                    changes.append(f"склад: {sclad_from} → {sclad_to}")
            prev_by_order[doc_order_id] = (status_id, pay_status_id, delivery_status_id, debet, kredit, discount, date_out, current_sclad_id)

            if row_user_id == user_id and day <= dt.date() < next_day:
                results.append({
                    "dttm": dt.isoformat(),
                    "order_num": order_num_by_id.get(doc_order_id, ""),
                    "summary": _humanize_order_action(
                        (basis or "").strip(),
                        sclad_changed=sclad_changed,
                        sclad_from=sclad_from,
                        sclad_to=sclad_to,
                    ),
                    "changes": changes,
                    "raw": (basis or "").strip(),
                })

        results.sort(key=lambda r: r["dttm"])
        return results

    def get_users_list(self, search: str = "") -> list[dict]:
        """Load {user_id, description} list from USERS table for matching with bot employees."""
        if not FIREBIRD_AVAILABLE:
            return []
        sql = "SELECT users.user_id, users.description FROM users"
        params: list = []
        search = (search or "").strip()
        if search:
            sql += " WHERE UPPER(users.description) LIKE UPPER(?)"
            params.append(f"%{search}%")
        sql += " ORDER BY users.description"
        try:
            conn = _connect()
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = [{"user_id": r[0], "description": (r[1] or "").strip()} for r in cur.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.warning(f"get_users_list error: {e}")
            return []

    def get_smses(self, date_from=None, date_to=None) -> list[dict]:
        """Load SMS records from SMSES table."""
        if not FIREBIRD_AVAILABLE:
            return []
        conditions = []
        params = []
        if date_from:
            conditions.append("CAST(DTTM AS DATE) >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("CAST(DTTM AS DATE) <= ?")
            params.append(date_to)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT FIRST 2000
                ID, DTTM, PHONE, TXT, OPER_STATUS,
                PUSH_ID, WAZZUP_MAX_ACCEPT, WAZZUP_MAX_SEND, SMS_STATUS
            FROM SMSES
            {where}
            ORDER BY DTTM DESC
        """
        try:
            conn = _connect()
            cur = conn.cursor()
            cur.execute(sql, params)
            cols = [c[0] for c in cur.description]
            rows = []
            for r in cur.fetchall():
                row = dict(zip(cols, r))
                if hasattr(row.get("DTTM"), "isoformat"):
                    row["DTTM"] = row["DTTM"].isoformat()
                if row.get("PUSH_ID") not in (None, "", 0):
                    row["channel"] = "Push"
                elif (
                    row.get("WAZZUP_MAX_ACCEPT") not in (None, "", 0)
                    or row.get("WAZZUP_MAX_SEND") not in (None, "", 0)
                ):
                    row["channel"] = "MAX"
                elif row.get("SMS_STATUS") in (0, 255, -255):
                    row["channel"] = "СМС"
                else:
                    row["channel"] = "—"
                rows.append(row)
            conn.close()
            return rows
        except Exception as e:
            logger.warning(f"get_smses error: {e}")
            return []


_firebird_service: FirebirdService | None = None


def get_firebird_service() -> FirebirdService:
    global _firebird_service
    if _firebird_service is None:
        _firebird_service = FirebirdService()
    return _firebird_service
