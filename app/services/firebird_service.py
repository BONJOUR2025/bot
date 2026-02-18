"""Firebird database connection service for sales data."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Generator

try:
    import fdb
    FIREBIRD_AVAILABLE = True
except ImportError:
    fdb = None
    FIREBIRD_AVAILABLE = False

from app.settings import settings

logger = logging.getLogger(__name__)


class FirebirdService:
    """Service for connecting to Firebird database and querying sales data."""

    def __init__(
        self,
        database: str | None = None,
        user: str | None = None,
        password: str | None = None,
        charset: str | None = None,
    ) -> None:
        self.database = database or settings.firebird_database
        self.user = user or settings.firebird_user
        self.password = password or settings.firebird_password
        self.charset = charset or settings.firebird_charset

    @contextmanager
    def connection(self) -> Generator[Any, None, None]:
        """Context manager for database connection."""
        if not FIREBIRD_AVAILABLE:
            raise RuntimeError("fdb library not installed. Run: pip install fdb")

        conn = None
        try:
            conn = fdb.connect(
                database=self.database,
                user=self.user,
                password=self.password,
                charset=self.charset,
            )
            yield conn
        finally:
            if conn:
                conn.close()

    def _parse_employee_code(self, description: str | None) -> str | None:
        """Extract 4-digit employee code from description like 'Имя 1234'."""
        if not description:
            return None
        description = str(description).strip()
        parts = description.split()
        if parts:
            last_part = parts[-1]
            if len(last_part) == 4 and last_part.isdigit():
                return last_part
        return None

    def get_repair_sales(
        self, date_from: date, date_to: date
    ) -> dict[str, float]:
        """
        Get repair/dry cleaning sales by employee.
        Returns dict: {employee_code: total_sales}
        """
        if not FIREBIRD_AVAILABLE:
            logger.warning("Firebird not available, returning empty sales data")
            return {}

        folder_ids = (
            215, 216, 217, 221, 326, 327, 328, 329, 330, 416, 417, 418, 419,
            108401, 108402, 110409, 110410, 110411, 210266, 210267, 210268,
            210269, 210270, 210271, 210272, 210273, 210274, 210275, 210276,
            210277, 210278, 210279, 210280, 210281, 210282, 210283, 210284,
            210285, 210286, 210287, 210288, 210289, 210290, 210291, 210292,
            210293, 210294, 210295, 210296, 210297, 210298, 210299, 210300,
            210301, 210302, 210303, 210304, 210305, 210306, 210307, 210308,
            210309, 210310, 210311, 210312, 210313, 210314, 210315, 210316,
            210317, 210318, 210319, 210320, 210321, 210322, 210323, 210324,
            210325, 210326, 210327, 210328, 210329, 210330, 210331, 210332,
            210333, 210334, 210335, 210336, 210337, 210338, 210339, 210340,
            210341, 210342, 210343, 210344, 210345, 210346, 210347, 210348,
            210349, 210350, 210351, 210352, 210353, 210355, 210356, 210357,
            210358, 210359, 210360, 210361, 210363, 210364, 210365, 210366,
            210377, 210378, 210379, 210380, 210381, 210382, 210383, 210384,
            210385, 210386, 210387, 210388, 210389, 210390, 210391, 210392,
            210393, 210394, 210395, 210396, 210397, 210399,
        )

        query = f"""
            SELECT
                users.description,
                SUM(doc_order_services.kredit) as total_sales
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE
                tovars_tbl.folder_id IN ({','.join(str(x) for x in folder_ids)})
                AND docs.doc_date BETWEEN ? AND ?
            GROUP BY users.description
        """

        result: dict[str, float] = {}
        try:
            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (date_from, date_to))
                for row in cursor.fetchall():
                    description, total = row
                    code = self._parse_employee_code(description)
                    if code and total:
                        result[code] = float(total)
        except Exception as e:
            logger.error(f"Error fetching repair sales: {e}")

        return result

    def get_cosmetics_sales(
        self, date_from: date, date_to: date
    ) -> dict[str, float]:
        """
        Get cosmetics sales by employee.
        Returns dict: {employee_code: total_sales}
        """
        if not FIREBIRD_AVAILABLE:
            logger.warning("Firebird not available, returning empty sales data")
            return {}

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

        query = f"""
            SELECT
                users.description,
                SUM(doc_order_lines.kredit) as total_sales
            FROM doc_order_lines
                INNER JOIN docs_order ON (doc_order_lines.doc_order_id = docs_order.id)
                INNER JOIN docs_order_history ON (docs_order.id = docs_order_history.doc_order_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN tovars_tbl ON (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN users ON docs_order.creater_id = users.user_id
            WHERE
                docs_order_history.status_id = 5
                AND docs.doc_date BETWEEN ? AND ?
                AND tovars_tbl.folder_id IN ({','.join(str(x) for x in folder_ids)})
            GROUP BY users.description
        """

        result: dict[str, float] = {}
        try:
            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (date_from, date_to))
                for row in cursor.fetchall():
                    description, total = row
                    code = self._parse_employee_code(description)
                    if code and total:
                        result[code] = float(total)
        except Exception as e:
            logger.error(f"Error fetching cosmetics sales: {e}")

        return result

    def get_shoes_sales(
        self, date_from: date, date_to: date
    ) -> dict[str, float]:
        """
        Get shoes sales by employee.
        Returns dict: {employee_code: total_sales}
        """
        if not FIREBIRD_AVAILABLE:
            logger.warning("Firebird not available, returning empty sales data")
            return {}

        query = """
            SELECT
                users.description,
                SUM(doc_order_services.kredit) as total_sales
            FROM docs_order
                INNER JOIN doc_order_services ON (docs_order.id = doc_order_services.doc_order_id)
                INNER JOIN tovars_tbl ON (doc_order_services.tovar_id = tovars_tbl.tovar_id)
                INNER JOIN docs ON (docs_order.doc_id = docs.doc_id)
                INNER JOIN users ON (docs_order.creater_id = users.user_id)
            WHERE
                tovars_tbl.code IN ('1', '147.10', '147.5')
                AND docs.doc_date BETWEEN ? AND ?
            GROUP BY users.description
        """

        result: dict[str, float] = {}
        try:
            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (date_from, date_to))
                for row in cursor.fetchall():
                    description, total = row
                    code = self._parse_employee_code(description)
                    if code and total:
                        result[code] = float(total)
        except Exception as e:
            logger.error(f"Error fetching shoes sales: {e}")

        return result

    def get_all_sales(
        self, date_from: date, date_to: date
    ) -> dict[str, dict[str, float]]:
        """
        Get all sales data for a period.
        Returns: {employee_code: {repair: X, cosmetics: Y, shoes: Z}}
        """
        repair = self.get_repair_sales(date_from, date_to)
        cosmetics = self.get_cosmetics_sales(date_from, date_to)
        shoes = self.get_shoes_sales(date_from, date_to)

        all_codes = set(repair.keys()) | set(cosmetics.keys()) | set(shoes.keys())

        result = {}
        for code in all_codes:
            result[code] = {
                "repair": repair.get(code, 0.0),
                "cosmetics": cosmetics.get(code, 0.0),
                "shoes": shoes.get(code, 0.0),
            }

        return result


_firebird_service: FirebirdService | None = None


def get_firebird_service() -> FirebirdService:
    global _firebird_service
    if _firebird_service is None:
        _firebird_service = FirebirdService()
    return _firebird_service
