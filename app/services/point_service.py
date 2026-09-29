"""Кабинет точки на рабочем ПК салона — данные экрана смены.

Точка — салон из «Салонов», её склады приёма — salon.sclad_ids (для Бестужевской
добавляем и склад приёмки в том же здании). Всё только чтение Агбиса; своё —
отметки звонков (point_device_repository.PointCallRepository).

Три списка, на которые смена смотрит весь день:
- «Выдача» — заказы точки в статусе «Исполненный»: изделие готово, клиент ещё
  не забрал. Позвонить надо тем, по кому ещё нет отметки звонка.
- «Сроки» — не готовые заказы со сроком сегодня или раньше: клиента нужно
  предупредить до того, как он приедет.
- «Долго лежат» — готовы больше STALE_DAYS дней назад и до сих пор не выданы.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

STALE_DAYS = 14
DUE_WINDOW_DAYS = 60
READY = 4
OPEN_STATUSES = (1, 2, 3)


def point_sclads(salon) -> list[int]:
    from app.services.workshop_order_service import BESTUZHEVSKAYA_SCLADS

    ids = {int(x) for x in (getattr(salon, "sclad_ids", None) or [])}
    if ids & BESTUZHEVSKAYA_SCLADS:
        ids |= BESTUZHEVSKAYA_SCLADS
    return sorted(ids)


def _money(v) -> float:
    try:
        return round(float(v or 0), 2)
    except Exception:
        return 0.0


def orders(salon) -> dict[str, Any]:
    from app.services.firebird_service import _connect
    from app.services.workshop_order_service import _iso, _text

    sclads = point_sclads(salon)
    if not sclads:
        return {"ready": [], "due": [], "sclads": []}
    now = datetime.now()
    today_end = datetime.combine(date.today(), datetime.max.time())
    con = _connect()
    try:
        cur = con.cursor()
        marks = ",".join("?" * len(sclads))
        cur.execute(
            f"""
            SELECT dor.id, d.doc_num, d.doc_date, dor.status_id, dor.date_out, dor.date_complete,
                   dor.kredit, dor.debet, dor.current_sclad_id, dor.fast_execute, d.contragent_id,
                   c.name, c.teleph_cell, dor.contact_tel1
            FROM docs_order dor
                JOIN docs d ON d.doc_id = dor.doc_id
                LEFT JOIN contragents c ON c.contr_id = d.contragent_id
            WHERE dor.sclad_kredit_id IN ({marks})
              AND (dor.status_id = {READY}
                   OR (dor.status_id IN ({",".join(map(str, OPEN_STATUSES))}) AND dor.date_out <= ?))
              AND d.doc_date > DATEADD(-400 DAY TO CURRENT_DATE)
            """, (*sclads, today_end))
        rows = cur.fetchall()
        ids = [r[0] for r in rows]

        # Что изделия — по одной строке-изделию на заказ, чтобы в списке было
        # «Туфли, Сумка», а не номер без смысла.
        items: dict[int, list[str]] = {}
        sms: dict[int, dict[str, Any]] = {}
        for start in range(0, len(ids), 200):
            chunk = ids[start:start + 200]
            m = ",".join("?" * len(chunk))
            cur.execute(
                f"SELECT dos.doc_order_id, t.name FROM doc_order_services dos "
                f"LEFT JOIN tovars_tbl t ON t.tovar_id = dos.tovar_id "
                f"WHERE dos.doc_order_id IN ({m}) AND dos.parent_dos_id IS NULL ORDER BY dos.id", chunk)
            for oid, name in cur.fetchall():
                n = _text(name)
                if n:
                    items.setdefault(oid, []).append(n)
        doc_ids = {}
        if ids:
            for start in range(0, len(ids), 200):
                chunk = ids[start:start + 200]
                m = ",".join("?" * len(chunk))
                cur.execute(f"SELECT id, doc_id FROM docs_order WHERE id IN ({m})", chunk)
                doc_ids.update({doc: oid for oid, doc in cur.fetchall()})
            docs = list(doc_ids)
            for start in range(0, len(docs), 200):
                chunk = docs[start:start + 200]
                m = ",".join("?" * len(chunk))
                cur.execute(
                    f"SELECT doc_id, dt_added, dt_deliver FROM smses WHERE doc_id IN ({m}) ORDER BY dt_added", chunk)
                for doc, added, delivered in cur.fetchall():
                    oid = doc_ids.get(doc)
                    if oid is not None:
                        sms[oid] = {"sent": _iso(added), "delivered": _iso(delivered)}
    finally:
        con.close()

    from app.data.point_device_repository import PointCallRepository
    from app.services.workshop_order_service import sclad_label

    calls = PointCallRepository().last_for(ids)
    ready, due = [], []
    for (oid, num, ddate, status, date_out, completed, kredit, debet, cur_sclad, fast, cid,
         cname, cphone, tel1) in rows:
        due_dt = date_out if isinstance(date_out, datetime) and date_out.year > 2000 else None
        row = {
            "order_id": oid,
            "doc_num": _text(num),
            "accepted": _iso(ddate),
            "items": items.get(oid, []),
            "client": _text(cname),
            "phone": _text(cphone) or _text(tel1),
            "to_pay": max(0.0, _money(kredit) - _money(debet)),
            "total": _money(kredit),
            "urgent": bool(fast),
            "due": _iso(due_dt),
            "location": sclad_label(cur_sclad),
            "sms": sms.get(oid),
            "call": calls.get(oid),
        }
        if status == READY:
            done = completed if isinstance(completed, datetime) else None
            row["ready_since"] = _iso(done)
            row["ready_days"] = (now - done).days if done else None
            row["stale"] = bool(done and (now - done) >= timedelta(days=STALE_DAYS))
            ready.append(row)
        else:
            row["overdue_days"] = (now.date() - due_dt.date()).days if due_dt else None
            due.append(row)
    ready.sort(key=lambda r: (r["call"] is not None, r["ready_since"] or ""))
    # Просрочка старше DUE_WINDOW_DAYS — это уже не «предупредить клиента до
    # приезда», а забытые заказы (часто индивидуальный пошив): отдельным счётчиком.
    old_due = [r for r in due if (r["overdue_days"] or 0) > DUE_WINDOW_DAYS]
    due = [r for r in due if (r["overdue_days"] or 0) <= DUE_WINDOW_DAYS]
    due.sort(key=lambda r: r["due"] or "")
    return {"ready": ready, "due": due, "old_due_count": len(old_due), "sclads": sclads}


def shift(salon) -> dict[str, Any]:
    """Кто сегодня отметился на точке (та же отметка, что приходит из бота)."""
    from app.data.employee_repository import EmployeeRepository
    from app.data.shift_checkin_repository import get_shift_checkin_repository

    today = date.today().isoformat()
    rows = get_shift_checkin_repository().list(date_from=today, date_to=today, salon_id=salon.id)
    emps = EmployeeRepository()
    people, seen = [], set()
    for r in sorted(rows, key=lambda x: x.get("sent_at", "")):
        eid = str(r.get("employee_id") or "")
        if eid in seen:
            continue
        seen.add(eid)
        e = emps.get_employee(eid)
        people.append({"name": (e.name if e else "") or r.get("employee_name") or "Сотрудник",
                       "at": r.get("sent_at")})
    return {"opened": bool(people), "people": people}
