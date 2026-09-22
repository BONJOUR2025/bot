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
1107 → 21021, 11017 → 21020, 11019 → 21016.
"""
from __future__ import annotations

import logging
import statistics
import time
from datetime import date, datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

REPAIR_POINTS: dict[int, str] = {21021: "Цех", 21020: "Пассаж", 21016: "Академ Парк"}

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
                   d.doc_date, dor.date_out
            FROM doc_order_services dos
                JOIN docs_order dor ON dor.id = dos.doc_order_id
                JOIN docs d ON d.doc_id = dor.doc_id
                JOIN tovars_tbl t ON t.tovar_id = dos.tovar_id
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

    now = datetime.now()
    out = []
    for sid, doc_num, name, kredit, sclad, doc_date, date_out in rows:
        due = date_out if isinstance(date_out, datetime) and date_out.year > 2000 else None
        accepted = doc_date if isinstance(doc_date, (date, datetime)) else None
        waiting = (now.date() - (accepted.date() if isinstance(accepted, datetime) else accepted)).days \
            if accepted else None
        out.append({
            "service_id": sid,
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


def build_overview() -> dict[str, Any]:
    from app.services import master_bot_service as mbs
    from app.services.masters_service import get_apprentice_stipends

    now = datetime.now()
    today = now.date()
    people = _people()
    month, prev = _services()
    by_id: dict[Any, dict] = {}
    for svc in prev + month:  # месяц перекрывает прошлый — он свежее
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
