"""Цех глазами старшего мастера: что требует внимания прямо сейчас.

Всё здесь только читает Агбис — ни одной записи. Основа та же, что у
кабинета мастера (master_bot_service): прогретый кэш masters.works за текущий
и прошлый месяц, а сверху — точечные запросы по первичным ключам (сроки и
комментарии заказов, турникет за сегодня) и один запрос за очередью.

Разделы ответа:
- wip        — всё, что сейчас «в работе» у мастеров, со сроками и комментариями;
- queue      — изделия, которые лежат в месте ремонта, но их никто не взял
               (нет ни одного скана на постах);
- masters    — по каждому мастеру: в работе, сделано за день / неделю / месяц,
               медиана времени, ошибки сканов, на смене ли. Заработка здесь
               нет намеренно: старший мастер видит объём работы, а не чужую
               зарплату;
- scan_issues — ошибки сканов: вход без выхода при готовом заказе (мастер
               теряет процент), выход без входа, слишком быстро, несколько
               сканов, разные мастера на входе и выходе;
- apprentices — дни обучения учеников за месяц (без денег).

Ремонт идёт в трёх местах, у каждого свои посты входа и выхода: центральный
цех и две точки. Их склады — это WORK_PLACES.SCLAD_ID постов входа (WP_IN):
1107 → 21021 «Бестужевская ЦЕХ», 11017 → 21020 «Гранд Палас» (пост по-старому
называется «ПАССАЖ»), 11019 → 21016 «Академическая».
"""
from __future__ import annotations

import logging
import statistics
import time
from datetime import date, datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

REPAIR_POINTS: dict[int, str] = {21021: "Цех", 21020: "Гранд Палас", 21016: "Академическая"}

ORDER_STATUS_LABEL = {3: "в исполнении", 4: "готов", 5: "выдан", 6: "закрыт", 7: "отменён"}
# Заказ готов или выдан, а скана выхода по услуге нет — процент мастеру не
# начислится (он считается по скану выхода). Отменённый заказ сюда не входит.
READY_STATUSES = {4, 5, 6}

STALE_WIP_DAYS = 7
QUEUE_LOOKBACK_DAYS = 60
# Медиана времени — без услуг короче 15 минут, как в панели «Мастера»:
# быстрые сканы подряд — это привычка сканировать бирку, а не работа.
MEDIAN_MIN_MINUTES = 15

CACHE_TTL_SECONDS = 120
_cache: dict[str, tuple[float, dict]] = {}

ISSUE_LABELS = {
    "no_out": "Вход без выхода, а заказ уже {status}",
    "no_in": "Выход без входа",
    "too_fast": "Слишком быстро",
    "multi": "Несколько сканирований",
    "mismatch": "Вход и выход у разных мастеров",
}


def _dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _uid(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _people() -> dict[int, dict[str, str]]:
    """Сотрудники по коду Агбиса (external_code) — только по числовому id,
    как и в кабинете мастера: строковые имена в Агбисе расходятся с карточками."""
    from app.data.employee_repository import EmployeeRepository

    out: dict[int, dict[str, str]] = {}
    for e in EmployeeRepository().list_employees(archived=False):
        code = str(getattr(e, "external_code", "") or "").strip()
        if code.isdigit():
            out[int(code)] = {
                "employee_id": str(e.id),
                "name": (e.full_name or e.name or "").strip(),
                "short": (e.name or e.full_name or "").strip(),
                "position": str(getattr(e, "position", "") or ""),
            }
    return out


def _services() -> tuple[list[dict], list[dict]]:
    """Услуги текущего и прошлого месяца из прогретого кэша."""
    from app.services import master_bot_service as mbs

    month = mbs._load_services(mbs.PERIOD_MONTH)
    try:
        prev = mbs._load_services(mbs.PERIOD_PREV_MONTH)
    except Exception:
        logger.warning("workshop: прошлый месяц из кэша не получен", exc_info=True)
        prev = []
    return month, prev


def _turnstile_today() -> dict[int, datetime]:
    """Кто сегодня отметился на турникете: код Агбиса → первое время входа."""
    from app.services.firebird_service import _connect

    today = date.today()
    con = _connect()
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT dre.user_id, MIN(dre.dt_in) FROM doc_registr_employees dre "
            "WHERE dre.dt_in >= ? AND dre.dt_in < ? "
            "AND (dre.is_delete IS NULL OR dre.is_delete = 0) GROUP BY dre.user_id",
            (str(today), str(today + timedelta(days=1))),
        )
        return {int(uid): first for uid, first in cur.fetchall() if uid is not None}
    finally:
        con.close()


def _queue() -> list[dict[str, Any]]:
    """Изделия в месте ремонта без единого скана на постах — их никто не взял.

    Заказ в исполнении, услуга не отменена, изделие числится на складе одного
    из мест ремонта, по услуге нет ни входа, ни выхода. Только зарплатные
    папки (те же, что в отчёте мастеров): продажа крема сюда не попадает.
    """
    from app.services.firebird_service import _connect
    from app.services.masters_service import WP_IN, WP_OUT, _SALARY_FOLDERS_SQL

    posts = ",".join(str(p) for p in sorted(WP_IN | WP_OUT))
    points = ",".join(str(p) for p in REPAIR_POINTS)
    con = _connect()
    try:
        cur = con.cursor()
        cur.execute(
            f"""
            SELECT dos.id, d.doc_num, t.name, dos.kredit, dos.current_sclad_id,
                   d.doc_date, dor.date_out, COALESCE(dos.parent_dos_id, dos.id),
                   CAST(top.name AS VARCHAR(200) CHARACTER SET OCTETS)
            FROM doc_order_services dos
                JOIN docs_order dor ON dor.id = dos.doc_order_id
                JOIN docs d ON d.doc_id = dor.doc_id
                JOIN tovars_tbl t ON t.tovar_id = dos.tovar_id
                LEFT JOIN tree folder ON folder.folder_id = t.folder_id
                LEFT JOIN tree top ON top.folder_id = folder.top_parent
            WHERE t.folder_id IN ({_SALARY_FOLDERS_SQL})
              AND d.doc_date > DATEADD(-{QUEUE_LOOKBACK_DAYS} DAY TO CURRENT_DATE)
              AND dor.status_id = 3
              AND (dos.status_id IS NULL OR dos.status_id <> 7)
              AND dos.current_sclad_id IN ({points})
              AND NOT EXISTS (
                  SELECT 1 FROM user_session_actions a
                  WHERE a.doc_order_services_id = dos.id AND a.work_place_id IN ({posts}))
            """
        )
        rows = cur.fetchall()
    finally:
        con.close()

    from app.services.master_bot_service import deadline
    from app.services.workshop_order_service import _text

    now = datetime.now()
    out = []
    for sid, doc_num, name, kredit, sclad, doc_date, date_out, item_id, top in rows:
        if _is_tailoring(_text(top)):
            continue
        due = date_out if isinstance(date_out, datetime) and date_out.year > 2000 else None
        accepted = doc_date if isinstance(doc_date, (date, datetime)) else None
        waiting = (now.date() - (accepted.date() if isinstance(accepted, datetime) else accepted)).days \
            if accepted else None
        out.append({
            "service_id": sid,
            "item_id": item_id,
            "doc_num": str(doc_num or ""),
            "name": str(name or ""),
            "kredit": _num(kredit),
            "point": REPAIR_POINTS.get(sclad, f"склад {sclad}"),
            "accepted": accepted.isoformat() if accepted else None,
            "waiting_days": waiting,
            **deadline(due, now),
        })
    out.sort(key=lambda r: (_due_rank(r), r["due"] or "9999", -(r["waiting_days"] or 0)))
    return out


_DUE_RANK = {"overdue": 0, "today": 1, "tomorrow": 2}


def _due_rank(row: dict) -> int:
    return _DUE_RANK.get(row.get("due_state"), 3)


def _issue(kind: str, svc: dict, people: dict, **extra) -> dict[str, Any]:
    uid = _uid(svc.get("out_user_id")) if kind == "no_in" else _uid(svc.get("in_user_id"))
    person = people.get(uid or -1)
    when = svc.get("out_time") if kind == "no_in" else (svc.get("in_time") or svc.get("out_time"))
    label = ISSUE_LABELS[kind]
    if kind == "no_out":
        label = label.format(status=ORDER_STATUS_LABEL.get(extra.get("order_status_id"), "закрыт"))
    detail = ""
    if kind == "too_fast":
        detail = f"{round(_num(svc.get('duration_min')), 1)} мин между входом и выходом"
    elif kind == "multi":
        detail = f"входов: {svc.get('in_count') or 0}, выходов: {svc.get('out_count') or 0}"
    elif kind == "mismatch":
        detail = f"вход — {svc.get('in_description') or '—'}, выход — {svc.get('out_description') or '—'}"
    elif kind == "no_out":
        detail = "выход не отсканирован — процент мастеру не начислится"
    return {
        "kind": kind,
        "label": label,
        "detail": detail,
        "service_id": svc.get("service_id"),
        "doc_num": svc.get("doc_num"),
        "name": svc.get("name"),
        "kredit": _num(svc.get("kredit")),
        "master": (person or {}).get("name") or svc.get("in_description") or svc.get("out_description") or "",
        "master_uid": uid,
        "when": when,
    }


SHOE_REPAIR_TOP = "ремонт обуви"
# Заказы, принятые курьером (склад «Курьер»), едут в цех без накладной и
# числятся уже на складе цеха — их руководитель тоже считает «в цеху».
COURIER_SCLAD = 21023
ADVICE_MIN_EXPERIENCE = 3   # столько выходов по ремонту обуви за 2 месяца — уже «ремонтник»

# Индивидуальный пошив («4.0 Услуги по инд. пошиву») делает отдельный отдел со
# своим руководителем — в цехе его не показываем нигде.
TAILORING_WORD = "пошив"

# Должность решает, кому можно отдать ремонт обуви: мастер по химчистке его не
# делает, даже если пара его сканов по ремонту в базе есть (подменял, помогал).
# Кого считаем ремонтником — по должности из карточки сотрудника.
REPAIR_POSITION_WORDS = ("ремонт", "подошв", "ученик", "старший мастер")
OTHER_POSITION_WORDS = ("химчист", TAILORING_WORD, "администратор", "курьер", "менеджер", "приём")


def _is_tailoring(top_name: Any) -> bool:
    return TAILORING_WORD in str(top_name or "").lower()


def _repairs_shoes(position: str) -> Optional[bool]:
    """Ремонтник ли по должности: True/False, либо None — должность неизвестна."""
    low = (position or "").strip().lower()
    if not low:
        return None
    if any(w in low for w in REPAIR_POSITION_WORDS):
        return True
    if any(w in low for w in OTHER_POSITION_WORDS):
        return False
    return None


def _workshop_shoe_queue() -> list[dict[str, Any]]:
    """Ремонт обуви, который лежит в цехе и который ещё никто не взял.

    «В цехе» — так, как считает руководитель: заказ принят на Бестужевской
    (склад цеха или приёмка в том же здании), последняя накладная по
    изделию везёт его в цех, или это курьерский заказ, который числится на
    складе цеха. Если после приёма на Бестужевской изделие уехало по
    накладной на точку — оно уже не в цехе. «Не взял» — ни одного скана на
    постах ремонта.
    """
    from app.services.firebird_service import _connect
    from app.services.masters_service import WP_IN, WP_OUT, _SALARY_FOLDERS_SQL
    from app.services.workshop_order_service import BESTUZHEVSKAYA_SCLADS, WORKSHOP_SCLAD, _text

    posts = ",".join(str(p) for p in sorted(WP_IN | WP_OUT | {1087}))
    # Накладная перевозит изделие (строку-родителя), а не отдельную услугу:
    # по самим услугам строк в DOCS_IN_WAY_SERVS почти нет.
    last_move = (
        "(SELECT FIRST 1 w.{col} FROM docs_in_way_servs s JOIN docs_in_way w ON w.id = s.doc_in_way_id "
        "WHERE s.dos_id = COALESCE(dos.parent_dos_id, dos.id) ORDER BY w.doc_date DESC, w.id DESC)"
    )
    con = _connect()
    try:
        cur = con.cursor()
        cur.execute(
            f"""
            SELECT dos.id, COALESCE(dos.parent_dos_id, dos.id), d.doc_num, t.name, dos.kredit,
                   CAST(folder.name AS VARCHAR(200) CHARACTER SET OCTETS),
                   CAST(top.name AS VARCHAR(200) CHARACTER SET OCTETS),
                   d.doc_date, dor.date_out, dor.sclad_kredit_id, dor.fast_execute, dos.current_sclad_id,
                   {last_move.format(col="to_sclad_id")}, {last_move.format(col="diw_status_id")}
            FROM doc_order_services dos
                JOIN docs_order dor ON dor.id = dos.doc_order_id
                JOIN docs d ON d.doc_id = dor.doc_id
                JOIN tovars_tbl t ON t.tovar_id = dos.tovar_id
                LEFT JOIN tree folder ON folder.folder_id = t.folder_id
                LEFT JOIN tree top ON top.folder_id = folder.top_parent
            WHERE t.folder_id IN ({_SALARY_FOLDERS_SQL})
              AND d.doc_date > DATEADD(-{QUEUE_LOOKBACK_DAYS} DAY TO CURRENT_DATE)
              AND dor.status_id IN (1, 3)
              AND (dos.status_id IS NULL OR dos.status_id NOT IN (4, 5, 6, 7))
              AND NOT EXISTS (
                  SELECT 1 FROM user_session_actions a
                  WHERE a.doc_order_services_id = dos.id AND a.work_place_id IN ({posts}))
            """
        )
        rows = cur.fetchall()
    finally:
        con.close()

    from app.services.master_bot_service import deadline

    now = datetime.now()
    out = []
    for (sid, item_id, doc_num, name, kredit, folder, top, doc_date, date_out, accepted_at, fast, current,
         last_to, last_status) in rows:
        if SHOE_REPAIR_TOP not in _text(top).lower():
            continue
        if last_to is not None:
            in_workshop = last_to == WORKSHOP_SCLAD and last_status in (2, 3, 4)
            how = "едет в цех по накладной" if last_status == 2 else "привезли по накладной"
        elif accepted_at == COURIER_SCLAD:
            in_workshop = current == WORKSHOP_SCLAD
            how = "курьерский заказ, числится в цехе"
        else:
            in_workshop = accepted_at in BESTUZHEVSKAYA_SCLADS
            how = "принят на Бестужевской"
        if not in_workshop:
            continue
        due = date_out if isinstance(date_out, datetime) and date_out.year > 2000 else None
        accepted = doc_date if isinstance(doc_date, (date, datetime)) else None
        accepted_day = accepted.date() if isinstance(accepted, datetime) else accepted
        out.append({
            "service_id": sid, "item_id": item_id, "doc_num": _text(doc_num), "name": _text(name),
            "kredit": _num(kredit),
            "folder": _text(folder), "how": how, "urgent": bool(fast),
            "waiting_days": (now.date() - accepted_day).days if accepted_day else None,
            **deadline(due, now),
        })
    out.sort(key=lambda r: (_due_rank(r), not r["urgent"], r["due"] or "9999", -(r["waiting_days"] or 0)))
    return out


def _advice(queue: list[dict], services: list[dict], stats: dict[int, dict],
            on_shift: Optional[dict], people: Optional[dict[int, dict]] = None) -> dict[str, Any]:
    """Кому какой заказ дать: срочные — первыми, каждому — наименее загруженный
    из тех, кто на смене и уже делал такую работу.

    В совет попадают только мастера по ремонту (должность из карточки
    сотрудника): химчистка и индивидуальный пошив — другие люди и другая
    работа, и раздавать им ремонт обуви нельзя, даже если в базе есть их
    случайные сканы по ремонту.

    Опыт — выходы по ремонту обуви за текущий и прошлый месяц, по папке услуги
    («01. Набойки», «Профилактика»…). Нагрузка — сколько у мастера сейчас в
    работе плюс то, что ему уже посоветовали в этом же расчёте, иначе все
    заказы достались бы одному самому свободному.
    """
    people = people or {}
    experience: dict[int, dict[str, int]] = {}
    outs: dict[int, int] = {}
    days: dict[int, set] = {}
    for svc in services:
        uid = _uid(svc.get("out_user_id"))
        done = _dt(svc.get("out_time"))
        if uid is not None and done:
            outs[uid] = outs.get(uid, 0) + 1
            days.setdefault(uid, set()).add(done.date())
        if uid is None or SHOE_REPAIR_TOP not in str(svc.get("top_parent_name") or "").lower():
            continue
        bucket = experience.setdefault(uid, {})
        folder = str(svc.get("folder_name") or "")
        bucket[folder] = bucket.get(folder, 0) + 1
        bucket["__total"] = bucket.get("__total", 0) + 1

    def position_of(uid: int) -> str:
        return (people.get(uid) or {}).get("position") or (stats.get(uid) or {}).get("position") or ""

    pool = [uid for uid, e in experience.items()
            if e["__total"] >= ADVICE_MIN_EXPERIENCE and _repairs_shoes(position_of(uid)) is not False]
    shift_known = on_shift is not None
    working = [uid for uid in pool if shift_known and uid in on_shift]
    candidates = working or pool
    planned: dict[int, int] = {uid: 0 for uid in pool}

    def per_day(uid: int) -> float:
        """Сколько мастер обычно сдаёт за рабочий день (все категории)."""
        worked = len(days.get(uid) or ())
        return (outs.get(uid, 0) / worked) if worked else 1.0

    def load(uid: int) -> int:
        return (stats.get(uid) or {}).get("wip", 0) + planned[uid]

    def backlog(uid: int) -> float:
        """Через сколько рабочих дней мастер разгребёт то, что у него уже есть.

        Считать нагрузку штуками — значит отдавать всё ученикам: у них меньше
        всего в работе, но и сдают они в разы медленнее. Амбарцумов с 23
        изделиями и десятью в день свободнее ученика с пятью.
        """
        return load(uid) / max(per_day(uid), 0.5)

    def name(uid: int) -> str:
        return (stats.get(uid) or {}).get("name") or f"Агбис {uid}"

    # Одна пара — один мастер: услуги изделия не раздаются разным людям.
    # Изделия идут в порядке самой срочной своей услуги (очередь уже
    # отсортирована), главная работа изделия — самая дорогая услуга.
    groups: dict[Any, list[dict]] = {}
    for svc in queue:
        groups.setdefault(svc["item_id"], []).append(svc)

    rows = []
    for services_of_item in groups.values():
        head = services_of_item[0]
        main = max(services_of_item, key=lambda x: x["kredit"])
        folders = {x["folder"] for x in services_of_item}
        item = {**head, "services": services_of_item, "folder": main["folder"], "main": main["name"],
                "kredit": sum(x["kredit"] for x in services_of_item)}
        if not candidates:
            rows.append({**item, "recommended": None, "alternatives": []})
            continue
        folder = main["folder"]

        def skill(u: int) -> int:
            return sum(experience[u].get(f, 0) for f in folders)

        skilled = [u for u in candidates if experience[u].get(folder, 0) > 0]
        ranked = sorted(skilled or candidates,
                        key=lambda u: (round(backlog(u), 1), -skill(u), -experience[u]["__total"]))
        best = ranked[0]
        did = experience[best].get(folder, 0)
        reason = (f"делал «{folder}» {did} раз за 2 месяца" if did else "такую работу не делал, но самый свободный") \
            + f"; в работе {load(best)}, сдаёт ~{per_day(best):.0f} в день — очередь на {backlog(best):.1f} дн"
        rows.append({
            **item,
            "recommended": {"master_uid": best, "name": name(best), "reason": reason},
            "alternatives": [{"master_uid": u, "name": name(u), "load": load(u),
                              "backlog_days": round(backlog(u), 1),
                              "did": experience[u].get(folder, 0)} for u in ranked[1:3]],
        })
        planned[best] += len(services_of_item)

    return {
        "queue": rows,
        "masters": sorted(({
            "master_uid": u, "name": name(u), "position": position_of(u),
            "wip": (stats.get(u) or {}).get("wip", 0),
            "planned": planned.get(u, 0), "on_shift": bool(shift_known and u in on_shift),
            "experience": experience[u]["__total"], "per_day": round(per_day(u), 1),
            "backlog_days": round(backlog(u), 1),
        } for u in pool), key=lambda m: (not m["on_shift"], m["backlog_days"])),
        "shift_known": shift_known,
        "only_on_shift": bool(working),
    }


# Миниатюры — только в списках, где мастер выбирает, что взять, и не больше
# THUMBS_LIMIT изделий на список: пара снимков на изделие — это килобайты, а
# сотня изделий с фото — уже мегабайты в одном ответе.
THUMBS_LIMIT = 80


def _attach_photos(*lists: Optional[list[dict]]) -> None:
    """Дописывает `photos` изделиям в переданных списках (одним запросом)."""
    from app.services.workshop_order_service import thumbs

    rows = [row for items in lists if items for row in items[:THUMBS_LIMIT] if row.get("item_id")]
    if not rows:
        return
    found = thumbs([row["item_id"] for row in rows])
    for row in rows:
        row["photos"] = found.get(row["item_id"], [])


def build_overview() -> dict[str, Any]:
    from app.services import master_bot_service as mbs
    from app.services.masters_service import get_apprentice_stipends

    now = datetime.now()
    today = now.date()
    people = _people()
    month, prev = _services()
    by_id: dict[Any, dict] = {}
    for svc in prev + month:  # месяц перекрывает прошлый — он свежее
        if _is_tailoring(svc.get("top_parent_name")):
            continue  # индивидуальный пошив — не цех
        by_id[svc.get("service_id")] = svc
    services = list(by_id.values())

    open_rows = [s for s in services if s.get("status") == "В работе"]
    closed_no_out = [s for s in services
                     if s.get("status") == "Выполнено" and s.get("in_time") and not s.get("out_time")]
    details = mbs._order_details(
        [s.get("service_id") for s in open_rows + closed_no_out], with_photos=False)

    # ── в работе ────────────────────────────────────────────────────────
    wip: list[dict] = []
    issues: list[dict] = []
    for svc in open_rows:
        extra = details.get(svc.get("service_id")) or {}
        order_status = extra.get("order_status_id")
        if order_status in READY_STATUSES:
            issues.append(_issue("no_out", svc, people, order_status_id=order_status))
            continue
        if order_status == 7:
            continue  # заказ отменён — в работе он только по сканам
        uid = _uid(svc.get("in_user_id"))
        person = people.get(uid or -1)
        started = _dt(svc.get("in_time"))
        wip.append({
            "service_id": svc.get("service_id"),
            "doc_num": svc.get("doc_num"),
            "name": svc.get("name"),
            "kredit": _num(svc.get("kredit")),
            "master": (person or {}).get("name") or svc.get("in_description") or "",
            "master_uid": uid,
            "in_time": svc.get("in_time"),
            "days": (today - started.date()).days if started else None,
            "urgent": str(svc.get("code") or "").startswith("144."),
            **mbs.deadline(extra.get("due"), now),
            "comments": extra.get("comments") or [],
        })
    wip.sort(key=mbs._wip_order)

    for svc in closed_no_out:
        order_status = (details.get(svc.get("service_id")) or {}).get("order_status_id")
        if order_status in READY_STATUSES:
            issues.append(_issue("no_out", svc, people, order_status_id=order_status))

    # «Слишком быстро» (меньше 3 минут между входом и выходом) списком не
    # выводим: на живых данных это 9 из 10 записей, у химчистки потоком — сотни
    # за месяц, и за ними теряются ошибки, из-за которых мастер недополучает
    # деньги. Такие сканы считаются по мастеру отдельной цифрой.
    fast: list[dict] = []
    for svc in services:
        for flag, kind in (("warning_no_in", "no_in"), ("warning_multi", "multi"),
                           ("warning_mismatch", "mismatch")):
            if svc.get(flag):
                issues.append(_issue(kind, svc, people))
        if svc.get("warning_too_fast"):
            fast.append(_issue("too_fast", svc, people))
    issues.sort(key=lambda i: str(i.get("when") or ""), reverse=True)

    # ── мастера ─────────────────────────────────────────────────────────
    try:
        on_shift = _turnstile_today()
    except Exception:
        logger.warning("workshop: турникет за сегодня не получен", exc_info=True)
        on_shift = None

    month_start = today.replace(day=1)
    week_start = today - timedelta(days=6)
    stats: dict[int, dict[str, Any]] = {}

    def row(uid: int, fallback: str) -> dict[str, Any]:
        if uid not in stats:
            person = people.get(uid) or {}
            stats[uid] = {
                "master_uid": uid,
                "name": person.get("name") or fallback or f"Агбис {uid}",
                "position": person.get("position") or "",
                "wip": 0, "wip_sum": 0.0, "overdue": 0, "stale": 0,
                "today": 0, "today_sum": 0.0, "week": 0, "week_sum": 0.0,
                "month": 0, "month_sum": 0.0, "durations": [], "issues": 0, "fast": 0,
                "on_shift": None if on_shift is None else uid in on_shift,
                "shift_from": (on_shift or {}).get(uid).isoformat(timespec="minutes")
                if on_shift and uid in on_shift else None,
            }
        return stats[uid]

    for item in wip:
        if item["master_uid"] is None:
            continue
        r = row(item["master_uid"], item["master"])
        r["wip"] += 1
        r["wip_sum"] += item["kredit"]
        r["overdue"] += item.get("due_state") == "overdue"
        r["stale"] += (item.get("days") or 0) >= STALE_WIP_DAYS
    for svc in services:
        uid = _uid(svc.get("out_user_id"))
        done = _dt(svc.get("out_time"))
        if uid is None or not done:
            continue
        r = row(uid, svc.get("out_description") or "")
        kredit = _num(svc.get("kredit"))
        d = done.date()
        if d == today:
            r["today"] += 1
            r["today_sum"] += kredit
        if d >= week_start:
            r["week"] += 1
            r["week_sum"] += kredit
        if d >= month_start:
            r["month"] += 1
            r["month_sum"] += kredit
            dur = svc.get("duration_min")
            if dur is not None and _num(dur) >= MEDIAN_MIN_MINUTES:
                r["durations"].append(_num(dur))
    for bucket, key in ((issues, "issues"), (fast, "fast")):
        for issue in bucket:
            uid = issue.get("master_uid")
            when = _dt(issue.get("when"))
            if uid is not None and when and when.date() >= month_start:
                row(uid, issue.get("master") or "")[key] += 1
    masters = []
    for r in stats.values():
        durations = r.pop("durations")
        r["median_min"] = round(statistics.median(durations)) if durations else None
        masters.append(r)
    masters.sort(key=lambda r: (-r["wip"], -r["month"]))

    # ── очередь ─────────────────────────────────────────────────────────
    try:
        queue = _queue()
    except Exception:
        logger.warning("workshop: очередь не получена", exc_info=True)
        queue = None

    # ── совет: кому какой ремонт обуви дать ───────────────────────────
    try:
        advice = _advice(_workshop_shoe_queue(), services, stats, on_shift, people)
    except Exception:
        logger.warning("workshop: совет по распределению не собран", exc_info=True)
        advice = None

    # ── миниатюры изделий для списков ───────────────────────────────────
    try:
        _attach_photos((advice or {}).get("queue"), queue)
    except Exception:
        logger.warning("workshop: миниатюры не получены", exc_info=True)

    # ── ученики ─────────────────────────────────────────────────────────
    try:
        raw = get_apprentice_stipends(month_start, today)
        apprentices = [{
            "employee_id": a["employee_id"],
            "name": a["name"],
            "days_count": a["days_count"],
            "days": a["days"],
            "today": any(d["date"] == today.isoformat() for d in a["days"]),
        } for a in raw]
    except Exception:
        logger.warning("workshop: ученики не получены", exc_info=True)
        apprentices = None

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "wip": wip,
        "queue": queue,
        "masters": masters,
        "scan_issues": issues[:300],
        "fast_scans_month": sum(r["fast"] for r in stats.values()),
        "apprentices": apprentices,
        "advice": advice,
        "points": list(REPAIR_POINTS.values()),
    }


def get_overview(refresh: bool = False) -> dict[str, Any]:
    cached = _cache.get("overview")
    if cached and not refresh and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    data = build_overview()
    _cache["overview"] = (time.monotonic(), data)
    return data


def invalidate() -> None:
    _cache.clear()
