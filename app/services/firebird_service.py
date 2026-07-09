"""Firebird database connection service for sales data."""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any, Optional

try:
    import fdb
    FIREBIRD_AVAILABLE = True
except ImportError:
    fdb = None
    FIREBIRD_AVAILABLE = False

from app.settings import settings

logger = logging.getLogger(__name__)

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
    return fdb.connect(
        dsn=f"{settings.firebird_host}/{settings.firebird_port}:{settings.firebird_database}",
        user=settings.firebird_user or "SYSDBA",
        password=settings.firebird_password or "masterkey",
        charset=settings.firebird_charset,
    )


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

REPAIR_FOLDER_IDS = (
    215, 216, 217, 221, 326, 327, 328, 329, 330, 416, 417, 418, 419,
    108401, 108402, 110409, 110410, 110411,
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

_PAIR_STARTERS = {'0', '1'}


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


    def get_daily_sales(self, date_from: date, date_to: date, salon_ids: list[str] | None = None) -> list[dict]:
        """
        Get daily repair + cosmetics sales by employee for a date range.
        Returns list of dicts: {date, code, description, repair, cosmetics, total}

        `salon_ids` (Salon.id values, e.g. from GET /api/salons/) restricts
        to orders resolved to one of those salons via the doc_num suffix
        (same attribution as get_department_comparison / "ФОТ по салонам").
        Orders that don't resolve to any salon are excluded when a filter
        is active — we can't confirm they belong to the selected ones.
        """
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty daily sales")
            return []
        salon_filter = set(salon_ids) if salon_ids else None

        repair_folder_ids = (
            215, 216, 217, 221, 326, 327, 328, 329, 330, 416, 417, 418, 419,
            108401, 108402, 110409, 110410, 110411,
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
        cosmetics_folder_ids = (
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

        shoes_sales_codes = tuple(c for c in SHOES_CODES if c not in ('0', '1'))
        shoes_placeholders = ','.join(['?'] * len(shoes_sales_codes))

        # key: (date_str, code) → {date, code, description, repair, cosmetics, shoes}
        result: dict[tuple, dict] = {}

        def _add(date_val, desc: str, amount, category: str) -> None:
            code = _code_from_description(desc)
            if not code:
                return
            date_str = date_val.isoformat() if hasattr(date_val, "isoformat") else str(date_val)
            key = (date_str, code)
            if key not in result:
                result[key] = {
                    "date": date_str,
                    "code": code,
                    "description": (desc or "").strip(),
                    "repair": 0.0,
                    "cosmetics": 0.0,
                    "shoes": 0.0,
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

        sql_cosmetics = f"""
            SELECT
                docs.doc_date,
                users.description,
                docs.doc_num,
                SUM(doc_order_lines.kredit)
            FROM doc_order_lines
                INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                INNER JOIN docs_order_history ON (docs_order.id = docs_order_history.doc_order_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE
                docs_order_history.status_id = 5
                AND docs.doc_date >= ?
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
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching daily sales: {e}")

        return [
            {**v, "total": v["repair"] + v["cosmetics"] + v["shoes"]}
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
        """Search CONTRAGENTS by name or phone.

        Excludes "Розница <салон>" accounts — generic walk-in buckets used
        when no specific client is registered (one such account can carry
        thousands of anonymous orders), which would swamp real clients in
        search results and make no sense in a client-level CRM.
        """
        if not FIREBIRD_AVAILABLE or not (query or "").strip():
            return []
        q = query.strip()
        sql = """
            SELECT FIRST ? contr_id, name, teleph_cell
            FROM contragents
            WHERE (UPPER(name) LIKE UPPER(?) OR teleph_cell LIKE ?)
                AND UPPER(name) NOT STARTING WITH 'РОЗНИЦА'
            ORDER BY name
        """
        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql, (limit, f"%{q}%", f"%{q}%"))
                rows = cur.fetchall()
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error searching clients: {e}")
            return []

        return [
            {"contragent_id": cid, "name": (name or "").strip(), "phone": (phone or "").strip() or None}
            for cid, name, phone in rows
        ]

    def get_client_profile(self, contragent_id: int) -> dict | None:
        """Full order history + LTV/avg-check/last-visit for one client."""
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
            "orders": [
                {"doc_num": o["doc_num"], "date": o["date"].isoformat(), "amount": round(o["amount"], 2)}
                for o in reversed(order_list)
            ],
        }

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
        sql_cosmetics = f"""
            SELECT users.description, tovars_tbl.tovar_id, docs.doc_date, docs.doc_num,
                   SUM(doc_order_lines.kredit), SUM(doc_order_lines.qty_kredit)
            FROM doc_order_lines
                INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                INNER JOIN docs_order_history ON (docs_order.id = docs_order_history.doc_order_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN users ON docs_order.creater_id = users.user_id
            WHERE
                docs_order_history.status_id = 5
                AND docs.doc_date >= ? AND docs.doc_date <= ?
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

    def get_turnaround_stats(self, date_from: date, date_to: date, salon_ids: list[str] | None = None) -> dict:
        """Order fulfillment time (order created → actually picked up) for a date range.

        Uses DOCS.DOC_DATE (order creation) vs DOCS_ORDER.DATE_OUT_FACT
        (actual pickup) — these have a much better fill rate for this
        business (~91% in a recent H1) than DATE_ORDER_START/EXECUTED
        (~10-15%). "Late" compares DATE_OUT_FACT against DATE_OUT, the
        date promised to the client.

        `salon_ids` restricts to orders resolved to one of those salons —
        see get_daily_sales for the attribution rule and its caveats. This
        forces the per-employee aggregation (avg/count/late) into Python
        instead of SQL GROUP BY, since a salon needs the individual doc_num
        resolved before it can be counted.
        """
        empty = {"total": {"avg_days": 0.0, "late_rate": 0.0, "order_count": 0}, "by_employee": []}
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty turnaround stats")
            return empty
        salon_filter = set(salon_ids) if salon_ids else None

        sql = """
            SELECT
                users.description, docs.doc_num, docs.doc_date,
                CAST(docs_order.date_out_fact AS TIMESTAMP) - CAST(docs.doc_date AS TIMESTAMP) AS days,
                CASE WHEN docs_order.date_out > DATE '2000-01-01'
                          AND CAST(docs_order.date_out_fact AS TIMESTAMP) > CAST(docs_order.date_out AS TIMESTAMP)
                     THEN 1 ELSE 0 END AS is_late
            FROM docs_order
                INNER JOIN docs ON (docs.doc_id = docs_order.doc_id)
                INNER JOIN users ON (users.user_id = docs_order.creater_id)
            WHERE
                docs.doc_date >= ? AND docs.doc_date <= ?
                AND docs_order.date_out_fact IS NOT NULL
                AND CAST(docs_order.date_out_fact AS TIMESTAMP) > CAST(docs.doc_date AS TIMESTAMP)
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
            logger.error(f"Error fetching turnaround stats: {e}")
            return empty

        by_emp: dict[str, dict] = {}
        with _SalonResolver() as resolve_salon:
            for desc, doc_num, doc_date, days, is_late in rows:
                if salon_filter is not None and resolve_salon(doc_num, doc_date) not in salon_filter:
                    continue
                code = _code_from_description(desc)
                if not code:
                    continue
                entry = by_emp.setdefault(code, {"code": code, "days_sum": 0.0, "order_count": 0, "late_count": 0})
                entry["days_sum"] += float(days or 0)
                entry["order_count"] += 1
                entry["late_count"] += is_late

        by_employee = []
        total_orders = 0
        total_late = 0
        total_days_weighted = 0.0
        for entry in by_emp.values():
            order_count = entry["order_count"]
            avg_days = entry["days_sum"] / order_count if order_count else 0.0
            late_count = entry["late_count"]
            by_employee.append({
                "code": entry["code"],
                "avg_days": round(avg_days, 1),
                "order_count": order_count,
                "late_count": late_count,
                "late_rate": round(late_count / order_count * 100, 1) if order_count else 0.0,
            })
            total_orders += order_count
            total_late += late_count
            total_days_weighted += avg_days * order_count

        by_employee.sort(key=lambda e: e["avg_days"], reverse=True)

        return {
            "total": {
                "avg_days": round(total_days_weighted / total_orders, 1) if total_orders else 0.0,
                "late_rate": round(total_late / total_orders * 100, 1) if total_orders else 0.0,
                "order_count": total_orders,
            },
            "by_employee": by_employee,
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
            amount = float(kredit or 0) - float(debet or 0)
            total_amount += amount
            orders.append({
                "doc_num": str(doc_num),
                "date": doc_date.isoformat() if hasattr(doc_date, "isoformat") else str(doc_date),
                "order_id": order_id,
                "pay_status_id": pay_status_id,
                "amount": round(amount, 2),
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

    def get_returns_summary(self, date_from: date, date_to: date, salon_ids: list[str] | None = None) -> dict:
        """Returned-order counts/amounts by employee for a date range (DOCS_ORDER.RETURNED=1).

        Read-only report — deliberately not wired into payroll bonuses/
        penalties. Whether a return should cost an employee money is a
        case-by-case call for a human, not something to automate from a
        raw RETURNED flag.

        `salon_ids` restricts to orders resolved to one of those salons —
        see get_daily_sales for the attribution rule and its caveats.
        """
        empty = {"total": {"return_count": 0, "return_amount": 0.0, "order_count": 0, "return_rate": 0.0}, "by_employee": []}
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty returns summary")
            return empty
        salon_filter = set(salon_ids) if salon_ids else None

        sql_returns = """
            SELECT users.description, docs.doc_num, docs.doc_date, docs_order.kredit
            FROM docs_order
                INNER JOIN docs ON (docs.doc_id = docs_order.doc_id)
                INNER JOIN users ON (users.user_id = docs_order.creater_id)
            WHERE
                docs.doc_date >= ? AND docs.doc_date <= ?
                AND docs_order.returned = 1
        """
        sql_totals = """
            SELECT users.description, docs.doc_num, docs.doc_date
            FROM docs_order
                INNER JOIN docs ON (docs.doc_id = docs_order.doc_id)
                INNER JOIN users ON (users.user_id = docs_order.creater_id)
            WHERE docs.doc_date >= ? AND docs.doc_date <= ?
        """

        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql_returns, (date_from, date_to))
                return_rows = cur.fetchall()
                cur.execute(sql_totals, (date_from, date_to))
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
                               salon_ids: list[str] | None = None) -> dict[int, dict]:
        """Per-TOVAR_ID revenue/qty for a date range, merged across repair
        (DOC_ORDER_SERVICES) and cosmetics (DOC_ORDER_LINES). Shoes are
        excluded — SHOES_CODES are line items within a paired commission
        structure (see _parse_shoe_pairs), not standalone SKUs a "top
        products" ranking would mean anything for.

        `salon_ids` restricts to orders resolved to one of those salons —
        see get_daily_sales for the attribution rule and its caveats. Unlike
        the by-employee reports, this one does NOT add doc_num to the
        GROUP BY to support that: doing so once measured 26-55s (vs <2s)
        because a per-SKU aggregate that's normally a few hundred rows
        exploded into one row per (SKU, order) — tens of thousands of rows
        — even with no filter applied. Instead, when a filter is active, a
        cheap separate pass resolves which DOC_NUMs qualify and the normal
        tight per-SKU query is restricted to just those via a batched
        IN-list (same technique as the cost lookup in get_margin_summary).
        """
        repair_folders = ','.join(str(x) for x in REPAIR_FOLDER_IDS)
        cosmetics_folders = ','.join(str(x) for x in COSMETICS_FOLDER_IDS)
        salon_filter = set(salon_ids) if salon_ids else None

        con = _connect()
        try:
            cur = con.cursor()

            doc_num_allowlist: list[str] | None = None
            if salon_filter is not None:
                cur.execute(
                    "SELECT DISTINCT doc_num, doc_date FROM docs WHERE doc_date >= ? AND doc_date <= ?",
                    (date_from, date_to),
                )
                order_rows = cur.fetchall()
                doc_num_allowlist = []
                with _SalonResolver() as resolve_salon:
                    for doc_num, doc_date in order_rows:
                        if resolve_salon(doc_num, doc_date) in salon_filter:
                            doc_num_allowlist.append(str(doc_num))
                if not doc_num_allowlist:
                    return {}

            if doc_num_allowlist is None:
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
                rows = list(cur.fetchall())

                sql_cosmetics = f"""
                    SELECT tovars_tbl.tovar_id, tovars_tbl.name, tovars_tbl.code,
                           SUM(doc_order_lines.kredit), SUM(doc_order_lines.qty_kredit)
                    FROM doc_order_lines
                        INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                        INNER JOIN docs_order_history ON (docs_order.id = docs_order_history.doc_order_id)
                        INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                        INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
                    WHERE docs_order_history.status_id = 5
                        AND docs.doc_date >= ? AND docs.doc_date <= ?
                        AND tovars_tbl.folder_id IN ({cosmetics_folders})
                    GROUP BY tovars_tbl.tovar_id, tovars_tbl.name, tovars_tbl.code
                """
                cur.execute(sql_cosmetics, (date_from, date_to))
                rows += cur.fetchall()
            else:
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
                rows = _fetch_batched(cur, sql_repair_tpl, doc_num_allowlist, (date_from, date_to), batch=200)

                sql_cosmetics_tpl = f"""
                    SELECT tovars_tbl.tovar_id, tovars_tbl.name, tovars_tbl.code,
                           SUM(doc_order_lines.kredit), SUM(doc_order_lines.qty_kredit)
                    FROM doc_order_lines
                        INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                        INNER JOIN docs_order_history ON (docs_order.id = docs_order_history.doc_order_id)
                        INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                        INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
                    WHERE docs.doc_num IN ({{ph}})
                        AND docs_order_history.status_id = 5
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
                          salon_ids: list[str] | None = None) -> dict:
        """Top/bottom-selling SKUs and biggest risers/fallers vs the
        preceding period of equal length."""
        empty = {"top": [], "bottom": [], "rising": [], "falling": []}
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty top products")
            return empty

        try:
            current = self._product_revenue_rows(date_from, date_to, salon_ids)
            span = (date_to - date_from).days + 1
            prev_to = date_from - timedelta(days=1)
            prev_from = prev_to - timedelta(days=span - 1)
            previous = self._product_revenue_rows(prev_from, prev_to, salon_ids)
        except Exception as e:
            logger.error(f"Error fetching top products: {e}")
            return empty

        MIN_VOLUME = 1000.0  # ignore trivial amounts when ranking % swings — a
        # SKU going from 10₽ to 100₽ is a meaningless "900% rise"

        merged = []
        for tovar_id, p in current.items():
            prev_revenue = previous.get(tovar_id, {}).get("revenue", 0.0)
            pct_change = (
                round((p["revenue"] - prev_revenue) / prev_revenue * 100, 1)
                if prev_revenue else None
            )
            merged.append({**p, "prev_revenue": round(prev_revenue, 2), "pct_change": pct_change,
                            "revenue": round(p["revenue"], 2), "qty": round(p["qty"], 1)})

        top = sorted(merged, key=lambda p: p["revenue"], reverse=True)[:limit]
        bottom = sorted((p for p in merged if p["revenue"] > 0), key=lambda p: p["revenue"])[:limit]

        swinging = [p for p in merged if p["pct_change"] is not None and max(p["revenue"], p["prev_revenue"]) >= MIN_VOLUME]
        rising = sorted(swinging, key=lambda p: p["pct_change"], reverse=True)[:limit]
        falling = sorted(swinging, key=lambda p: p["pct_change"])[:limit]

        return {"top": top, "bottom": bottom, "rising": rising, "falling": falling}

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

    def get_department_comparison(self, date_from: date, date_to: date, salon_ids: list[str] | None = None) -> dict:
        """Revenue/order comparison by salon for a date range.

        Salon attribution reuses the exact mechanism payroll_service's
        payroll-by-salon report uses — the -N suffix on DOCS.DOC_NUM,
        resolved via SalonRepository (time-aware for renamed/relocated
        points) — rather than DOCS.DEP_ID, so this can't silently disagree
        with that existing report over what counts as "salon X's revenue".

        `salon_ids`, if given, just restricts the *output* to those salons
        — the whole point of this endpoint is grouping by salon, so
        "filtering" here is a plain post-filter, not a resolution change.
        """
        from app.data.salon_repository import get_salon_repository

        UNALLOC_ID = "unallocated"
        UNALLOC_NAME = "Не определено"

        empty = {"total_revenue": 0.0, "departments": []}
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty department comparison")
            return empty

        repair_folders = ','.join(str(x) for x in REPAIR_FOLDER_IDS)
        cosmetics_folders = ','.join(str(x) for x in COSMETICS_FOLDER_IDS)
        shoes_sales_codes = tuple(c for c in SHOES_CODES if c not in ('0', '1'))
        shoes_placeholders = ','.join(['?'] * len(shoes_sales_codes))

        sql_repair = f"""
            SELECT docs.doc_num, docs.doc_date, SUM(doc_order_services.kredit)
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
            WHERE
                docs.doc_date >= ? AND docs.doc_date <= ?
                AND tovars_tbl.folder_id IN ({repair_folders})
            GROUP BY docs.doc_num, docs.doc_date
        """
        sql_cosmetics = f"""
            SELECT docs.doc_num, docs.doc_date, SUM(doc_order_lines.kredit)
            FROM doc_order_lines
                INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                INNER JOIN docs_order_history ON (docs_order.id = docs_order_history.doc_order_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
            WHERE
                docs_order_history.status_id = 5
                AND docs.doc_date >= ? AND docs.doc_date <= ?
                AND tovars_tbl.folder_id IN ({cosmetics_folders})
            GROUP BY docs.doc_num, docs.doc_date
        """
        sql_shoes = f"""
            SELECT docs.doc_num, docs.doc_date, SUM(doc_order_services.kredit)
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
            WHERE
                docs.doc_date >= ? AND docs.doc_date <= ?
                AND tovars_tbl.code IN ({shoes_placeholders})
            GROUP BY docs.doc_num, docs.doc_date
        """

        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql_repair, (date_from, date_to))
                rows = list(cur.fetchall())
                cur.execute(sql_cosmetics, (date_from, date_to))
                rows += cur.fetchall()
                cur.execute(sql_shoes, (date_from, date_to, *shoes_sales_codes))
                rows += cur.fetchall()
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
            for doc_num, doc_date, revenue in rows:
                code = _order_salon_code(doc_num)
                salon = repo.get_by_order_code(code, doc_date.year, doc_date.month) if code else None
                salon_id = salon.id if salon else UNALLOC_ID
                salon_name = salon.name if salon else UNALLOC_NAME
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
        """Load cash movements from DOC_KASSA_MOVES."""
        if not FIREBIRD_AVAILABLE:
            return []
        conditions = ["DK_DATE > DATE '2023-12-31'"]
        params: list = []
        if date_from:
            conditions.append("DK_DATE >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("DK_DATE <= ?")
            params.append(date_to)
        where = " AND ".join(conditions)
        sql = f"""
            SELECT ID_KASSES_MOVE, DK_DATE, SUMM, BASIS, OWN_USR_ID, DEP_SRC_ID
            FROM DOC_KASSA_MOVES
            WHERE {where}
            ORDER BY DK_DATE DESC
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
                rows.append(row)
            conn.close()
            return rows
        except Exception as e:
            logger.warning(f"get_cash_moves error: {e}")
            return []


    def get_cash_move_by_id(self, move_id: str) -> Optional[dict]:
        """Load a single cash movement by ID from DOC_KASSA_MOVES."""
        if not FIREBIRD_AVAILABLE:
            return None
        sql = """
            SELECT ID_KASSES_MOVE, DK_DATE, SUMM, BASIS, OWN_USR_ID, DEP_SRC_ID
            FROM DOC_KASSA_MOVES
            WHERE ID_KASSES_MOVE = ?
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
            return result
        except Exception as e:
            logger.warning(f"get_cash_move_by_id error: {e}")
            return None


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
