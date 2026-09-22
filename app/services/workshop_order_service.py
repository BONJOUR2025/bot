"""Карточка заказа для старшего мастера: поиск по номеру или бирке, всё о заказе.

Только чтение Агбиса. Ищем по номеру заказа («37441-7»), по номеру без
суффикса («37441» — если таких заказов несколько, возвращаем список) или по
штрихкоду бирки (18 или 14 цифр — как в скане мастера).

В карточке: шапка заказа (когда и где принят, срок, статус, где сейчас),
изделия с услугами, сканы на постах цеха по каждой услуге, комментарии
приёмщика, фото изделий и движение по накладным. Данные клиента (телефон,
фамилия) сюда не попадают: цеху они не нужны.
"""
from __future__ import annotations

import base64
import logging
import re
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)

WORKSHOP_SCLAD = 21021          # «3_Бестужевская ЦЕХ»
BESTUZHEVSKAYA_SCLADS = {21021, 21024}  # цех и приёмка в том же здании

STATUS_NAMES = {1: "Новый", 2: "На хранении", 3: "В исполнении", 4: "Исполненный",
                5: "Выданный", 6: "Закрытый", 7: "Отменённый"}
IN_WAY_STATUS = {1: "готова к отгрузке", 2: "в пути", 3: "принята", 4: "принята не полностью"}
MAX_PHOTOS_PER_ITEM = 8


class OrderNotFound(LookupError):
    pass


def _dec(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("cp1251", "replace")
    return value


def _text(value: Any) -> str:
    value = _dec(value)
    if value is None:
        return ""
    if hasattr(value, "read"):
        value = _dec(value.read())
    return re.sub(r"\s+", " ", str(value)).strip()


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return None


@lru_cache(maxsize=1)
def sclad_names() -> dict[int, str]:
    """Склады Агбиса: «3_Бестужевская» → «Бестужевская» (номер — служебный)."""
    from app.services.firebird_service import _connect

    con = _connect()
    try:
        cur = con.cursor()
        cur.execute("SELECT id, CAST(name AS VARCHAR(120) CHARACTER SET OCTETS) FROM sclads")
        out = {}
        for sid, name in cur.fetchall():
            label = re.sub(r"^\d+_", "", _text(name)).strip()
            out[sid] = label or f"склад {sid}"
        return out
    finally:
        con.close()


def sclad_label(sid: Any) -> Optional[str]:
    if sid is None:
        return None
    try:
        return sclad_names().get(int(sid), f"склад {sid}")
    except Exception:
        return f"склад {sid}"


def find(query: str) -> dict[str, Any]:
    """Что нашли по строке поиска: {"order_id"} или {"choices": [...]}.

    Бирка — 14 или 18 цифр подряд; номер заказа — «число-число» или просто
    число (тогда ищем все его суффиксы).
    """
    from app.services.firebird_service import _connect

    raw = (query or "").strip()
    digits = re.sub(r"\D", "", raw)
    con = _connect()
    try:
        cur = con.cursor()
        if re.fullmatch(r"\d{14}|\d{18}", raw.replace(" ", "")):
            column = "barcode" if len(digits) == 18 else "barcode14"
            cur.execute(f"SELECT FIRST 2 doc_order_id FROM doc_order_services WHERE {column} = ?", (digits,))
            rows = cur.fetchall()
            if rows:
                return {"order_id": rows[0][0]}
            raise OrderNotFound("Бирка не найдена в Агбисе.")
        m = re.fullmatch(r"(\d{2,7})\s*[-–/ ]\s*(\d{1,3})", raw)
        if m:
            cur.execute(
                "SELECT FIRST 2 dor.id FROM docs d JOIN docs_order dor ON dor.doc_id = d.doc_id "
                "WHERE d.doc_num = ?", (f"{m.group(1)}-{m.group(2)}",))
            rows = cur.fetchall()
            if rows:
                return {"order_id": rows[0][0]}
            raise OrderNotFound("Заказ с таким номером не найден.")
        if re.fullmatch(r"\d{2,7}", raw):
            cur.execute(
                "SELECT FIRST 12 dor.id, d.doc_num, d.doc_date, dor.sclad_kredit_id, dor.status_id "
                "FROM docs d JOIN docs_order dor ON dor.doc_id = d.doc_id "
                "WHERE d.doc_num STARTING WITH ? ORDER BY d.doc_date DESC", (f"{raw}-",))
            rows = cur.fetchall()
            if not rows:
                raise OrderNotFound("Заказ с таким номером не найден.")
            if len(rows) == 1:
                return {"order_id": rows[0][0]}
            return {"choices": [{
                "order_id": oid, "doc_num": _text(num), "date": _iso(d),
                "accepted_at": sclad_label(sk), "status": STATUS_NAMES.get(st, "—"),
            } for oid, num, d, sk, st in rows]}
        raise OrderNotFound("Введите номер заказа (например 37441-7) или отсканируйте бирку.")
    finally:
        con.close()


def card(order_id: int) -> dict[str, Any]:
    """Всё о заказе для экрана старшего мастера."""
    from app.services.firebird_service import _connect
    from app.services.master_bot_service import _order_details, deadline
    from app.services.master_scan_service import POST_IN, POST_OUT

    con = _connect()
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT d.doc_num, d.doc_date, d.doc_time, dor.status_id, dor.date_out, dor.sclad_kredit_id, "
            "       dor.current_sclad_id, dor.fast_execute, dor.ext_info, dor.defects, dor.kredit "
            "FROM docs_order dor JOIN docs d ON d.doc_id = dor.doc_id WHERE dor.id = ?", (order_id,))
        head = cur.fetchone()
        if not head:
            raise OrderNotFound("Заказ не найден.")
        doc_num, doc_date, doc_time, status, date_out, sclad_kredit, cur_sclad, fast, ext, defects, kredit = head

        cur.execute(
            """
            SELECT dos.id, dos.parent_dos_id, t.name, dos.kredit, dos.status_id, dos.current_sclad_id,
                   dos.current_work_place_id, dos.barcode, dos.ext_info, folder.name, top.name, t.folder_id
            FROM doc_order_services dos
                LEFT JOIN tovars_tbl t ON t.tovar_id = dos.tovar_id
                LEFT JOIN tree folder ON folder.folder_id = t.folder_id
                LEFT JOIN tree top ON top.folder_id = folder.top_parent
            WHERE dos.doc_order_id = ?
            ORDER BY dos.id
            """, (order_id,))
        lines = cur.fetchall()
        ids = [r[0] for r in lines]

        scans: dict[int, list[dict]] = {}
        places: dict[int, str] = {}
        if ids:
            marks = ",".join("?" * len(ids))
            cur.execute(
                f"""
                SELECT usa.doc_order_services_id, usa.date_beg, usa.work_place_id, us.user_id,
                       u.description, CAST(wp.name AS VARCHAR(120) CHARACTER SET OCTETS)
                FROM user_session_actions usa
                    JOIN user_session us ON us.id = usa.user_session_id
                    LEFT JOIN users u ON u.user_id = us.user_id
                    LEFT JOIN work_places wp ON wp.id = usa.work_place_id
                WHERE usa.doc_order_services_id IN ({marks})
                ORDER BY usa.date_beg
                """, ids)
            for dos_id, when, wp, uid, who, wp_name in cur.fetchall():
                scans.setdefault(dos_id, []).append({
                    "date": _iso(when), "post_id": wp, "post": _text(wp_name) or f"пост {wp}",
                    "kind": "in" if wp == POST_IN else "out" if wp == POST_OUT else "other",
                    "master": _text(who) or None, "master_uid": uid,
                })
            cur.execute(f"SELECT id, CAST(name AS VARCHAR(120) CHARACTER SET OCTETS) FROM work_places "
                        f"WHERE id IN (SELECT current_work_place_id FROM doc_order_services "
                        f"WHERE id IN ({marks}))", ids)
            places = {wid: _text(n) for wid, n in cur.fetchall()}

            cur.execute(
                f"""
                SELECT s.dos_id, d.doc_num, d.doc_date, d.from_sclad_id, d.to_sclad_id, d.diw_status_id,
                       s.date_in
                FROM docs_in_way_servs s JOIN docs_in_way d ON d.id = s.doc_in_way_id
                WHERE s.dos_id IN ({marks})
                ORDER BY d.doc_date, d.id
                """, ids)
            moves_raw = cur.fetchall()
        else:
            moves_raw = []

        items = sorted({(r[1] or r[0]) for r in lines})
        photos: dict[int, list[dict]] = {}
        if items:
            marks = ",".join("?" * len(items))
            cur.execute(
                f"SELECT p.dos_id, p.id, p.md5_checksum, p.small FROM doc_order_serv_photos p "
                f"WHERE p.dos_id IN ({marks}) ORDER BY p.dos_id, p.is_main_photo DESC, p.id", items)
            for item_id, pid, md5, small in cur.fetchall():
                bucket = photos.setdefault(item_id, [])
                if len(bucket) >= MAX_PHOTOS_PER_ITEM:
                    continue
                if isinstance(md5, bytes):
                    md5 = md5.decode("ascii", "replace")
                raw = small.read() if hasattr(small, "read") else small
                thumb = None
                if raw:
                    mime = "image/png" if raw[:4] == b"\x89PNG" else "image/jpeg"
                    thumb = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
                bucket.append({"id": pid, "md5": (md5 or "").strip(), "thumb": thumb})
    finally:
        con.close()

    service_ids = [r[0] for r in lines if r[1]]  # у услуги есть родитель-изделие
    details = _order_details(service_ids, with_photos=False) if service_ids else {}
    now = datetime.now()

    moves: dict[int, list[dict]] = {}
    for dos_id, num, d, frm, to, st, date_in in moves_raw:
        moves.setdefault(dos_id, []).append({
            "doc_num": _text(num), "date": _iso(d), "from": sclad_label(frm), "to": sclad_label(to),
            "to_workshop": to == WORKSHOP_SCLAD, "status": IN_WAY_STATUS.get(st, "—"), "received": _iso(date_in),
        })

    by_item: dict[int, dict] = {}
    from app.services.masters_service import SALARY_FOLDER_IDS

    for dos_id, parent, name, line_kredit, line_status, line_sclad, wp, barcode, line_ext, folder, top, folder_id in lines:
        if not parent:
            by_item[dos_id] = {
                "item_id": dos_id, "name": _text(name), "note": _text(line_ext),
                "photos": photos.get(dos_id, []), "services": [],
                "location": sclad_label(line_sclad),
            }
    for dos_id, parent, name, line_kredit, line_status, line_sclad, wp, barcode, line_ext, folder, top, folder_id in lines:
        if not parent:
            continue
        item = by_item.setdefault(parent, {"item_id": parent, "name": "Изделие", "note": "", "photos": photos.get(parent, []),
                                           "services": [], "location": None})
        extra = details.get(dos_id) or {}
        service_scans = scans.get(dos_id, [])
        item["services"].append({
            "service_id": dos_id,
            "name": _text(name),
            "category": _text(top),
            "folder": _text(folder),
            "kredit": float(line_kredit or 0),
            "status": STATUS_NAMES.get(line_status, "—"),
            "status_id": line_status,
            "location": sclad_label(line_sclad),
            "post": places.get(wp) if wp else None,
            "barcode": _text(barcode),
            # Работа мастера на посту (сдельная): только по ней есть смысл
            # ставить вход и выход. Консультации, товары и т.п. — нет.
            "workshop_work": folder_id in SALARY_FOLDER_IDS,
            "scans": service_scans,
            "has_in": any(s["kind"] == "in" for s in service_scans),
            "has_out": any(s["kind"] == "out" for s in service_scans),
            "comments": [c for c in (extra.get("comments") or [])],
            "moves": moves.get(dos_id, []),
        })

    due = date_out if isinstance(date_out, datetime) and date_out.year > 2000 else None
    accepted = datetime.combine(doc_date, doc_time) if isinstance(doc_date, date) and doc_time else doc_date
    return {
        "order_id": order_id,
        "doc_num": _text(doc_num),
        "accepted": _iso(accepted),
        "accepted_at": sclad_label(sclad_kredit),
        "accepted_at_workshop": sclad_kredit in BESTUZHEVSKAYA_SCLADS,
        "status": STATUS_NAMES.get(status, "—"),
        "status_id": status,
        "location": sclad_label(cur_sclad),
        "urgent": bool(fast),
        "note": _text(ext),
        "defects": _text(defects),
        "kredit": float(kredit or 0),
        **deadline(due, now),
        "items": [i for i in by_item.values() if i["services"] or i["photos"]],
    }


def thumbs(item_ids: list[int], per_item: int = 2) -> dict[int, list[dict]]:
    """Миниатюры изделий для списков цеха: {id строки-изделия: [{id, md5, thumb}]}.

    Те же снимки, что в карточке заказа, но по паре на изделие — список
    цеха грузится целиком, и полная пачка фото раздула бы ответ.
    """
    from app.services.firebird_service import _connect

    ids = [int(i) for i in dict.fromkeys(item_ids) if i is not None]
    if not ids:
        return {}
    out: dict[int, list[dict]] = {}
    con = _connect()
    try:
        cur = con.cursor()
        marks = ",".join("?" * len(ids))
        cur.execute(
            f"SELECT p.dos_id, p.id, p.md5_checksum, p.small FROM doc_order_serv_photos p "
            f"WHERE p.dos_id IN ({marks}) ORDER BY p.dos_id, p.is_main_photo DESC, p.id", ids)
        for item_id, pid, md5, small in cur.fetchall():
            bucket = out.setdefault(item_id, [])
            if len(bucket) >= per_item:
                continue
            if isinstance(md5, bytes):
                md5 = md5.decode("ascii", "replace")
            raw = small.read() if hasattr(small, "read") else small
            if not raw:
                continue
            mime = "image/png" if raw[:4] == b"\x89PNG" else "image/jpeg"
            bucket.append({"id": pid, "md5": (md5 or "").strip(),
                           "thumb": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"})
    finally:
        con.close()
    return out


def photo_exists(photo_id: int, md5: str) -> bool:
    """Снимок с таким id и хешем есть в базе (защита от перебора id)."""
    from app.services.firebird_service import _connect

    con = _connect()
    try:
        cur = con.cursor()
        cur.execute("SELECT md5_checksum FROM doc_order_serv_photos WHERE id = ?", (photo_id,))
        row = cur.fetchone()
    finally:
        con.close()
    if not row:
        return False
    stored = row[0].decode("ascii", "replace") if isinstance(row[0], bytes) else str(row[0] or "")
    return stored.strip().lower() == (md5 or "").strip().lower()
