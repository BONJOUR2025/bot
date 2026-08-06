"""Agbis LOCAL_OPTIONS / LOCAL_OPTION_VALUES for the "Настройки Agbis" admin page.

Agbis stores ~665 per-computer settings (LOCAL_OPTIONS = catalog with
description + default; LOCAL_OPTION_VALUES = per-LOCAL_COMPUTER_ID
override). Every option has a FOLDER_ID pointing into LOCAL_OPTIONS_TREE
(FOLDER_ID, PARENT_ID, NAME, ORDER_NUM) — this *is* the real category tree
Agbis's own "Настройки модуля" screen renders (root = tab, e.g. «Кассы/ФР»
→ «АТОЛ»), confirmed against production: resolving every option through
this tree drops the catch-all bucket from 98 (an earlier keyword-guessing
classifier invented for this page, since removed) down to 25 — matching
Agbis's own «Прочее» folder (53 rows) once the other 28 are also accounted
for by the vendor-inheritance rule below. There was no need to reverse
engineer Him.exe for this: the real category structure was sitting in the
database the whole time, just in a table this page never queried.

7 of 665 rows have FOLDER_ID = NULL (a handful of payment-terminal fields:
BankName/SberConnectionType for Sberbank, Inpas, Arcus, PosApi,
Bankomsvyaz, MtbBank). Every one of those GROUP_OPTION_NAMEs has 4-13
*other* rows that do have a real FOLDER_ID, so the orphan inherits its
group's folder rather than falling into an unlabeled bucket — not a guess,
just following the same vendor's own sibling settings to where Agbis
itself put them.
"""
from __future__ import annotations

import logging
import re
from collections import Counter

from app.services.firebird_service import FIREBIRD_AVAILABLE, _connect

logger = logging.getLogger(__name__)

_DB_NAME_RE = re.compile(r"ARM_(\w+?)\.fdb$", re.IGNORECASE)

# Sorts after every real tree-derived category — only hit if a future Agbis
# option ships with neither a FOLDER_ID nor a GROUP_OPTION_NAME any sibling
# already has a folder for (none of the current 665 need this).
_UNCATEGORIZED = "Без категории"
_UNCATEGORIZED_SORT_KEY = (10**9,)


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


def _build_breadcrumb_resolver(tree_rows):
    """tree_rows: (folder_id, parent_id, name, order_num) from
    LOCAL_OPTIONS_TREE. Returns a function folder_id -> (category, subgroup,
    sort_key):

    - category: the root of the path — this is the tab a human sees in
      Agbis's own settings dialog (e.g. «Кассы/ФР»).
    - subgroup: everything under the root, joined with " → " (e.g. «АТОЛ»),
      or None if the option sits directly under the root with no subfolder.
    - sort_key: each folder's own ORDER_NUM from root to leaf — reproduces
      Agbis's own menu order without needing any ordering of our own.

    Memoized per folder_id: 665 options resolve against only ~84 tree nodes,
    so repeated rows sharing a folder (the common case) do the walk once.
    """
    tree = {fid: (pid, name, onum) for fid, pid, name, onum in tree_rows}
    cache: dict[int, tuple[str | None, str | None, tuple]] = {}

    def resolve(folder_id):
        if folder_id is None:
            return None, None, ()
        if folder_id in cache:
            return cache[folder_id]
        names, orders = [], []
        fid, seen = folder_id, set()
        while fid is not None and fid in tree and fid not in seen:
            seen.add(fid)
            pid, name, onum = tree[fid]
            # A couple of tree nodes have a blank NAME in Agbis's own data
            # (e.g. FOLDER_ID 378 under «Кассы/ФР») — the node still counts
            # for ordering, it just contributes no breadcrumb text.
            nm = (name or "").strip()
            if nm:
                names.append(nm)
            orders.append(onum or 0)
            fid = pid
        orders.reverse()
        if not names:
            result = (None, None, tuple(orders))
        else:
            names.reverse()
            result = (names[0], " → ".join(names[1:]) or None, tuple(orders))
        cache[folder_id] = result
        return result

    return resolve


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
    """Every LOCAL_OPTION, grouped by Agbis's own LOCAL_OPTIONS_TREE
    category/subgroup, with the effective value for every registered Agbis
    POS computer (Him.exe installs only — Updater.exe/AgbisAgentTasks.exe/
    AgbisAgentGUI.exe rows share the same computer physically but aren't a
    "settings screen").
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

            cur.execute("SELECT FOLDER_ID, PARENT_ID, NAME, ORDER_NUM FROM LOCAL_OPTIONS_TREE")
            tree_rows = [(fid, pid, _decode(name), onum) for fid, pid, name, onum in cur.fetchall()]

            cur.execute("""
                SELECT ID, FOLDER_ID, GROUP_OPTION_NAME, OPTION_NAME, SHORT_DESCR, LONG_DESCR,
                       DEFAULT_BOOL, DEFAULT_INT, DEFAULT_STR, DEFAULT_FLOAT, ORDER_NUM
                FROM LOCAL_OPTIONS
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

    resolve = _build_breadcrumb_resolver(tree_rows)

    # Fallback folder for the handful of options whose own FOLDER_ID is
    # NULL: the folder most of that option's own vendor-group siblings use
    # (see module docstring — every current orphan has one).
    folder_votes: dict[str, Counter] = {}
    for row in option_rows:
        group, folder_id = _decode(row[2]), row[1]
        if group and folder_id is not None:
            folder_votes.setdefault(group, Counter())[folder_id] += 1
    group_fallback_folder = {
        group: counter.most_common(1)[0][0] for group, counter in folder_votes.items()
    }

    categories: dict[str, list[dict]] = {}
    category_sort_key: dict[str, tuple] = {}

    for (opt_id, folder_id, group, option_name, short_descr, long_descr,
         d_bool, d_int, d_str, d_float, own_order) in option_rows:
        group = _decode(group)
        option_name = _decode(option_name)
        short_descr = _decode(short_descr)
        long_descr = _decode(long_descr)
        d_str = _decode(d_str)
        descr = _best_description(option_name, short_descr, long_descr)

        effective_folder_id = folder_id if folder_id is not None else group_fallback_folder.get(group)
        category, subgroup, sort_key = resolve(effective_folder_id)
        if category is None:
            category, sort_key = _UNCATEGORIZED, _UNCATEGORIZED_SORT_KEY

        category_sort_key.setdefault(category, sort_key)

        values = {}
        for comp_id in computer_ids:
            v_bool, v_int, v_str, v_flt = values_by_key.get((opt_id, comp_id), (None, None, None, None))
            v_str = _decode(v_str)
            value, source = _effective_value(v_bool, v_int, v_str, v_flt, d_bool, d_int, d_str, d_float)
            values[str(comp_id)] = {"value": _decode(value), "source": source}

        categories.setdefault(category, []).append({
            "id": opt_id,
            "option_name": option_name,
            "short_descr": descr,
            "group": group,
            "subgroup": subgroup,
            "_sort": (sort_key, own_order or 0, option_name),
            "values": values,
        })

    ordered_categories = []
    for name in sorted(categories, key=lambda c: category_sort_key.get(c, _UNCATEGORIZED_SORT_KEY)):
        opts = sorted(categories[name], key=lambda o: o["_sort"])
        for o in opts:
            del o["_sort"]
        ordered_categories.append({"name": name, "options": opts})

    return {"computers": computers, "categories": ordered_categories}
