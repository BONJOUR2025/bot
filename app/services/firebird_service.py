"""Firebird database connection service for sales data."""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

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
    '1',
    '147.1', '147.2', '147.3', '147.4', '147.5', '147.6', '147.7',
    '147.8', '147.9', '147.10', '147.11', '147.12', '147.13', '147.14',
    '147.15', '147.16', '147.17', '147.18', '147.19', '147.20', '147.21', '147.22',
)


class FirebirdService:
    """Service for connecting to Firebird database and querying sales data."""

    def get_repair_sales(self, year: int, month: int) -> dict[str, float]:
        """
        Get repair/dry cleaning sales by employee for a given month.
        Returns dict: {employee_code: total_sales}
        """
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty repair sales")
            return {}

        start, end = _month_range(year, month)

        folder_ids = (
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

        sql = f"""
            SELECT
                users.description AS DESCRIPTION,
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
            GROUP BY users.description
        """

        out: dict[str, float] = {}
        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql, (start, end))
                for desc, s in cur.fetchall():
                    code = _code_from_description(desc)
                    if code:
                        out[code] = float(s or 0)
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching repair sales: {e}")

        return out

    def get_cosmetics_sales(self, year: int, month: int) -> dict[str, float]:
        """
        Get cosmetics sales by employee for a given month.
        Returns dict: {employee_code: total_sales}
        """
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty cosmetics sales")
            return {}

        start, end = _month_range(year, month)

        folder_ids = (
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

        sql = f"""
            SELECT
                users.description AS DESCRIPTION,
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
            GROUP BY users.description
        """

        out: dict[str, float] = {}
        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql, (start, end))
                for desc, s in cur.fetchall():
                    code = _code_from_description(desc)
                    if code:
                        out[code] = float(s or 0)
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching cosmetics sales: {e}")

        return out

    def get_shoes_data(self, year: int, month: int) -> dict[str, list[dict]]:
        """
        Get shoes sales per PAIR by employee for a given month.
        Each record with CODE='1' is one pair of shoes.
        Filters by docs_order.date_out_fact (actual delivery date) and STATUS_ID=5.
        Returns: {employee_code: [{doc_num: str, kredit: float}, ...]}

        Commission rule (applied in payroll_service):
          - Each row = 1 pair with its own KREDIT
          - kredit > 11000 → 1000 ₽
          - kredit <= 11000 → 500 ₽
        """
        if not FIREBIRD_AVAILABLE:
            logger.warning("fdb library not installed - returning empty shoes data")
            return {}

        start, end = _month_range(year, month)

        # Select each pair (CODE='1') individually, no grouping
        sql = """
            SELECT
                users.description AS DESCRIPTION,
                docs.doc_num AS DOC_NUM,
                doc_order_services.kredit AS KREDIT
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
                INNER JOIN docs_order_history ON (docs_order.id = docs_order_history.doc_order_id)
            WHERE
                docs_order.date_out_fact >= ?
                AND docs_order.date_out_fact < ?
                AND tovars_tbl.code = '1'
                AND docs_order_history.status_id = 5
        """

        out: dict[str, list[dict]] = {}
        try:
            con = _connect()
            try:
                cur = con.cursor()
                cur.execute(sql, (start, end))
                for desc, doc_num, kredit in cur.fetchall():
                    code = _code_from_description(desc)
                    if code and doc_num is not None:
                        out.setdefault(code, []).append({
                            "doc_num": str(doc_num),
                            "kredit": float(kredit or 0),
                        })
            finally:
                con.close()
        except Exception as e:
            logger.error(f"Error fetching shoes data: {e}")

        return out

    def get_all_sales(self, year: int, month: int) -> dict[str, dict]:
        """
        Get all sales data for a month including per-DOC_NUM shoes data.
        Returns: {employee_code: {repair: X, cosmetics: Y, shoes: Z, shoes_orders: [{doc_num, kredit}, ...]}}
        shoes_orders items: {"doc_num": str, "kredit": float}
        """
        repair = self.get_repair_sales(year, month)
        cosmetics = self.get_cosmetics_sales(year, month)
        shoes_data = self.get_shoes_data(year, month)

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
                "shoes_orders": shoes_data.get(code, []),
            }
            for code in all_codes
        }


_firebird_service: FirebirdService | None = None


def get_firebird_service() -> FirebirdService:
    global _firebird_service
    if _firebird_service is None:
        _firebird_service = FirebirdService()
    return _firebird_service
