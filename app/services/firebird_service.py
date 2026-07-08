"""Firebird database connection service for sales data."""
from __future__ import annotations

import logging
import re
from datetime import date
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


def _code_from_description(desc: str | None) -> str | None:
    """Extract 4-digit employee code from description like 'Имя 1234'."""
    desc = (desc or "").strip()
    m = CODE_RE.search(desc)
    return m.group(1) if m else None


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


    def get_daily_sales(self, date_from: date, date_to: date) -> list[dict]:
        """
        Get daily repair + cosmetics sales by employee for a date range.
        Returns list of dicts: {date, code, description, repair, cosmetics, total}
        """
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty daily sales")
            return []

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

        sql_repair = f"""
            SELECT
                docs.doc_date,
                users.description,
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
            GROUP BY docs.doc_date, users.description
            ORDER BY docs.doc_date, users.description
        """

        sql_cosmetics = f"""
            SELECT
                docs.doc_date,
                users.description,
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
            GROUP BY docs.doc_date, users.description
            ORDER BY docs.doc_date, users.description
        """

        sql_shoes = f"""
            SELECT
                CAST(docs.doc_date AS DATE),
                users.description,
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
            GROUP BY CAST(docs.doc_date AS DATE), users.description
            ORDER BY CAST(docs.doc_date AS DATE), users.description
        """

        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql_repair, (date_from, date_to))
                for d, desc, s in cur.fetchall():
                    _add(d, desc, s, "repair")
                cur.execute(sql_cosmetics, (date_from, date_to))
                for d, desc, s in cur.fetchall():
                    _add(d, desc, s, "cosmetics")
                cur.execute(sql_shoes, (date_from, date_to, *shoes_sales_codes))
                for d, desc, s in cur.fetchall():
                    if d is not None:
                        _add(d, desc, s, "shoes")
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching daily sales: {e}")

        return [
            {**v, "total": v["repair"] + v["cosmetics"] + v["shoes"]}
            for v in sorted(result.values(), key=lambda x: (x["date"], x["code"]))
        ]


    def get_client_retention(self, date_from: date, date_to: date) -> dict:
        """New-vs-returning client breakdown for a date range.

        A client is "returning" if their first-ever order (across all
        history) predates date_from, "new" otherwise. The first-ever-order
        lookup is a single ungrouped-by-date full scan (~3s regardless of
        range) rather than one lookup per client — a per-client correlated
        subquery was measured at 60-100s for a month/year range because it
        re-executes the MIN(doc_date) query once per distinct client.
        """
        empty = {"total_clients": 0, "new_clients": 0, "returning_clients": 0, "repeat_rate": 0.0}
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty client retention")
            return empty

        sql_active = """
            SELECT d.contragent_id, COUNT(DISTINCT do.id) AS orders_in_period
            FROM docs d
                INNER JOIN docs_order do ON (do.doc_id = d.doc_id)
            WHERE
                d.doc_date >= ?
                AND d.doc_date <= ?
                AND d.contragent_id IS NOT NULL
            GROUP BY d.contragent_id
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
                active = cur.fetchall()
                if not active:
                    return empty

                cur.execute(sql_first_order)
                first_order = dict(cur.fetchall())
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching client retention: {e}")
            return empty

        total = len(active)
        returning = sum(
            1 for contragent_id, _ in active
            if (first_order.get(contragent_id) or date_from) < date_from
        )
        new_clients = total - returning
        return {
            "total_clients": total,
            "new_clients": new_clients,
            "returning_clients": returning,
            "repeat_rate": round(returning / total * 100, 1) if total else 0.0,
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
