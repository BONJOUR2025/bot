import re
from datetime import date
import fdb

CODE_RE = re.compile(r"(\d{4})$")

def _code_from_description(desc: str) -> str | None:
    desc = (desc or "").strip()
    m = CODE_RE.search(desc)
    return m.group(1) if m else None

def _month_range(year: int, month: int) -> tuple[date, date]:
    if month == 12:
        return date(year, 12, 1), date(year + 1, 1, 1)
    return date(year, month, 1), date(year, month + 1, 1)

def _connect(settings):
    # Для локальной базы Agbis чаще всего host=localhost, user/pass могут быть пустые или SYSDBA/masterkey
    return fdb.connect(
        dsn=f"{settings.FDB_HOST}/{settings.FDB_PORT}:{settings.FDB_PATH}",
        user=(settings.FDB_USER or "SYSDBA"),
        password=(settings.FDB_PASS or "masterkey"),
        charset="UTF8",
    )

def get_sales_repair(settings, year: int, month: int) -> dict[str, float]:
    start, end = _month_range(year, month)
    sql = """
    select
        users.description as DESCRIPTION,
        sum(doc_order_services.kredit) as SUM_KREDIT
    from docs_order
        inner join doc_order_services on (docs_order.id = doc_order_services.doc_order_id)
        inner join tovars_tbl on (doc_order_services.tovar_id = tovars_tbl.tovar_id)
        inner join docs on (docs_order.doc_id = docs.doc_id)
        inner join users on (docs_order.creater_id = users.user_id)
    where
        docs.doc_date >= ?
        and docs.doc_date <  ?
        and tovars_tbl.folder_id in (215, 216, 217, 221, 326, 327, 328, 329, 330, 416, 417, 418, 419,
            108401, 108402, 110409, 110410, 110411,
            210266, 210267, 210268, 210269, 210270, 210271, 210272, 210273, 210274, 210275, 210276, 210277,
            210278, 210279, 210280, 210281, 210282, 210283, 210284, 210285, 210286, 210287, 210288, 210289,
            210290, 210291, 210292, 210293, 210294, 210295, 210296, 210297, 210298, 210299, 210300, 210301,
            210302, 210303, 210304, 210305, 210306, 210307, 210308, 210309, 210310, 210311, 210312, 210313,
            210314, 210315, 210316, 210317, 210318, 210319, 210320, 210321, 210322, 210323, 210324, 210325,
            210326, 210327, 210328, 210329, 210330, 210331, 210332, 210333, 210334, 210335, 210336, 210337,
            210338, 210339, 210340, 210341, 210342, 210343, 210344, 210345, 210346, 210347, 210348, 210349,
            210350, 210351, 210352, 210353, 210355, 210356, 210357, 210358, 210359, 210360, 210361, 210363,
            210364, 210365, 210366, 210377, 210378, 210379, 210380, 210381, 210382, 210383, 210384, 210385,
            210386, 210387, 210388, 210389, 210390, 210391, 210392, 210393, 210394, 210395, 210396, 210397,
            210399)
    group by users.description
    """
    out = {}
    con = _connect(settings)
    try:
        cur = con.cursor()
        cur.execute(sql, (start, end))
        for desc, s in cur.fetchall():
            code = _code_from_description(desc)
            if code:
                out[code] = float(s or 0)
    finally:
        con.close()
    return out

def get_sales_cosmetics(settings, year: int, month: int) -> dict[str, float]:
    start, end = _month_range(year, month)
    sql = """
    select
        users.description as DESCRIPTION,
        sum(doc_order_lines.kredit) as SUM_KREDIT
    from doc_order_lines
        inner join docs_order on (doc_order_lines.doc_order_id = docs_order.id)
        inner join docs_order_history on (docs_order.id = docs_order_history.doc_order_id)
        inner join docs on (docs_order.doc_id = docs.doc_id)
        inner join tovars_tbl on (doc_order_lines.tovar_id = tovars_tbl.tovar_id)
        inner join users on docs_order.creater_id = users.user_id
    where
        docs_order_history.status_id = 5
        and docs.doc_date >= ?
        and docs.doc_date <  ?
        and tovars_tbl.folder_id in (
            107,108,109,110,111,113,114,115,116,117,118,119,120,121,122,123,
            124,125,126,127,128,129,130,131,132,133,134,135,136,137,138,139,
            140,141,142,143,144,145,146,147,148,149,150,151,152,153,154,155,
            156,157,159,161,162,163,164,165,166,167,168,169,170,171,172,173,
            174,175,176,177,178,179,180,181,182,183,184,185,186,187,188,189,
            190,192,193,194,195,196,198,199,200,201,202,203,204,206,207,208,
            209,220,222,223,229,230,232,233,109407,110413,210234,210235,210236,
            210237,210241,210243,210244,210248,210249,210250,210254,210255,210258,
            210265,210398
        )
    group by users.description
    """
    out = {}
    con = _connect(settings)
    try:
        cur = con.cursor()
        cur.execute(sql, (start, end))
        for desc, s in cur.fetchall():
            code = _code_from_description(desc)
            if code:
                out[code] = float(s or 0)
    finally:
        con.close()
    return out

def get_sales_shoes(settings, year: int, month: int) -> dict[str, float]:
    start, end = _month_range(year, month)
    sql = """
    select
        users.description as DESCRIPTION,
        sum(doc_order_services.kredit) as SUM_KREDIT
    from docs_order
        inner join doc_order_services on (docs_order.id = doc_order_services.doc_order_id)
        inner join tovars_tbl on (doc_order_services.tovar_id = tovars_tbl.tovar_id)
        inner join docs on (docs_order.doc_id = docs.doc_id)
        inner join users on (docs_order.creater_id = users.user_id)
    where
        docs.doc_date >= ?
        and docs.doc_date <  ?
        and tovars_tbl.code in ('1', '147.10', '147.5')
    group by users.description
    """
    out = {}
    con = _connect(settings)
    try:
        cur = con.cursor()
        cur.execute(sql, (start, end))
        for desc, s in cur.fetchall():
            code = _code_from_description(desc)
            if code:
                out[code] = float(s or 0)
    finally:
        con.close()
    return out
