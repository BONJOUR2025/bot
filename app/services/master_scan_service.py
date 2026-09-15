"""Вход и выход по услугам из приложения мастера — ПРОБНЫЙ РЕЖИМ.

Модуль ничего не пишет в Агбис. Он находит услугу по бирке, проверяет
правила постов и собирает план записи — ровно те строки, которые пишет клиент
Агбиса при скане на посту, чтобы до включения записи сверить план с
настоящими сканами.

Что пишет клиент Агбиса при одном скане восстановлено по реальным сканам
Корягина 15.09.2026 (вход в цех 14:07, выход 15:37) и описано в
plan_writes(). Коротко, почему запись не делается «одним INSERT»:

- скан — это сессия мастера на посту, действие по бирке, строка о
  напарниках и строка истории действий, а не одна запись;
- статус, текущее место и склад услуги (и заказа) меняет сам клиент, не
  триггеры — без этого учёт разойдётся с отметкой;
- выход засчитывается только после входа (WORK_PLACES_BEFORE_WP), а повтор
  база сама помечает переделкой — это влияет на зарплату;
- все эти таблицы реплицируются в подразделения (MST_META_CHANGES_I), так
  что ошибочная строка разойдётся по всем базам.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable, Optional

POST_IN = 1107   # «1. Ремонт--->ВХОД Цех»
POST_OUT = 1108  # «2. Ремонт  ВЫХОД --->Цех»
ACTIONS = {"in": POST_IN, "out": POST_OUT}
# Перед выходом из цеха у услуги должен быть скан одного из этих постов
# (WORK_PLACES_BEFORE_WP: 1108 ← 1107, 1108 ← 1087).
POSTS_BEFORE_OUT = (POST_IN, 1087)

# ORDER_STATUSES — справочник Агбиса, общий для заказов и услуг.
STATUS_NAMES = {
    1: "Новый",
    2: "На хранении",
    3: "В исполнении",
    4: "Исполненный",
    5: "Выданный",
    6: "Закрытый",
    7: "Отменённый",
}
STATUS_IN_WORK = 3
STATUS_DONE = 4
CLOSED_STATUSES = {5, 6, 7}

# У всех наблюдаемых сканов цеха DEP_ID = LAST_DEP_ID = DEP_SRC_ID = 1.
DEP_ID = 1
# USER_ACTION_HIST.KIND_ID у скана на посту.
ACTION_HIST_KIND = 3

BARCODE_ERRORS = {
    "invalid_barcode": "Не похоже на номер бирки: нужно 18 цифр (или 14 последних).",
    "ambiguous_barcode": "По этому номеру нашлось несколько услуг — отсканируйте полный штрихкод.",
}

_SERVICE_COLUMNS = (
    "id", "doc_order_id", "status_id", "current_work_place_id", "current_sclad_id",
    "kredit", "kfx", "qty_kredit", "barcode", "name", "doc_num",
    "order_status_id", "order_current_sclad_id",
)


class BarcodeError(ValueError):
    """Номер бирки не годится для поиска — наверх идёт как HTTP 400."""


def normalize_barcode(raw: Any) -> str:
    """Только цифры: сканер и ручной ввод могут принести пробелы и дефисы."""
    return re.sub(r"\D", "", str(raw or ""))


def _dec(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        for encoding in ("utf-8", "cp1251"):
            try:
                return bytes(value).decode(encoding)
            except UnicodeDecodeError:
                continue
        return bytes(value).decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value.strip()
    return value


def _num(value: Any) -> Optional[float]:
    return float(value) if value is not None else None


def lookup(barcode: str, connect: Optional[Callable[[], Any]] = None) -> Optional[dict[str, Any]]:
    """Услуга по бирке, её сканы и посты цеха. Только SELECT.

    None — бирка не найдена. Поиск идёт по индексу (BARCODE для 18 цифр,
    BARCODE14 для 14), на проде — единицы миллисекунд.
    """
    code = normalize_barcode(barcode)
    if len(code) not in (14, 18):
        raise BarcodeError("invalid_barcode")
    if connect is None:
        from app.services.firebird_service import _connect as connect

    column = "dos.barcode" if len(code) == 18 else "dos.barcode14"
    con = connect()
    try:
        cur = con.cursor()
        cur.execute(
            f"""
            SELECT FIRST 2
                dos.id, dos.doc_order_id, dos.status_id, dos.current_work_place_id, dos.current_sclad_id,
                dos.kredit, dos.kfx, dos.qty_kredit, dos.barcode, t.name, d.doc_num,
                dor.status_id, dor.current_sclad_id
            FROM doc_order_services dos
                JOIN docs_order dor ON dor.id = dos.doc_order_id
                JOIN docs d ON d.doc_id = dor.doc_id
                LEFT JOIN tovars_tbl t ON t.tovar_id = dos.tovar_id
            WHERE {column} = ?
            """,
            (code,),
        )
        rows = cur.fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            raise BarcodeError("ambiguous_barcode")
        service = dict(zip(_SERVICE_COLUMNS, (_dec(v) for v in rows[0])))
        for key in ("kredit", "kfx", "qty_kredit"):
            service[key] = _num(service[key])

        cur.execute(
            """
            SELECT usa.id, usa.date_beg, usa.work_place_id, us.user_id, u.description
            FROM user_session_actions usa
                JOIN user_session us ON us.id = usa.user_session_id
                LEFT JOIN users u ON u.user_id = us.user_id
            WHERE usa.doc_order_services_id = ?
            ORDER BY usa.date_beg
            """,
            (service["id"],),
        )
        scans = [
            {
                "id": row[0],
                "date": row[1].isoformat() if hasattr(row[1], "isoformat") else row[1],
                "work_place_id": row[2],
                "user_id": row[3],
                "master": _dec(row[4]) or None,
            }
            for row in cur.fetchall()
        ]

        cur.execute(
            "SELECT id, name, proc, sclad_id FROM work_places WHERE id IN (?, ?, ?)",
            (POST_IN, POST_OUT, 1087),
        )
        posts = {
            row[0]: {"id": row[0], "name": _dec(row[1]), "proc": _num(row[2]), "sclad_id": row[3]}
            for row in cur.fetchall()
        }
    finally:
        con.close()
    return {"service": service, "scans": scans, "posts": posts}


def _fmt_dt(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(str(iso)).strftime("%d.%m %H:%M")
    except ValueError:
        return str(iso)


def check(found: dict[str, Any], action: str, master_user_id: int) -> dict[str, Any]:
    """Правила постов цеха для одного действия: что запрещено и о чём предупредить."""
    service, scans = found["service"], found["scans"]
    status = service.get("status_id")
    post = ACTIONS[action]
    blockers: list[str] = []
    warnings: list[str] = []

    if status in CLOSED_STATUSES:
        blockers.append(
            f"Услуга в статусе «{STATUS_NAMES.get(status, status)}» — сканировать её уже нельзя."
        )
    if action == "out" and not any(s["work_place_id"] in POSTS_BEFORE_OUT for s in scans):
        blockers.append("Входа в цех по этой бирке не было — сначала отсканируйте вход.")

    same_post = [s for s in scans if s["work_place_id"] == post]
    if same_post:
        last = same_post[-1]
        what = "Вход" if action == "in" else "Выход"
        who = last["master"] or "мастер не указан"
        warnings.append(
            f"{what} уже был {_fmt_dt(last['date'])} ({who}) — повторный скан Агбис посчитает переделкой."
        )
    if action == "in" and status == STATUS_DONE:
        warnings.append("Услуга уже исполнена.")
    if action == "out":
        ins = [s for s in scans if s["work_place_id"] == POST_IN]
        if ins and ins[-1]["user_id"] != master_user_id:
            warnings.append(
                f"Вход в цех делал другой мастер ({ins[-1]['master'] or 'не указан'}) — выход засчитается вам."
            )
    return {"allowed": not blockers, "blockers": blockers, "warnings": warnings}


def suggest_action(found: dict[str, Any]) -> str:
    """Что логично сейчас: после входа — выход, иначе — вход."""
    posts = [s["work_place_id"] for s in found["scans"] if s["work_place_id"] in (POST_IN, POST_OUT)]
    return "out" if posts and posts[-1] == POST_IN else "in"


def plan_writes(
    found: dict[str, Any], action: str, master_user_id: int, now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Строки, которые клиент Агбиса записал бы при этом скане.

    По наблюдению за реальными сканами: сессия на посту, строка напарников,
    действие (время начала и конца — момент скана, на выходе процент поста в
    WP_KOEF), строка истории действий, изменение услуги и её история. На входе
    ещё заказ переходит «в исполнение» на склад цеха и пишется его история.
    Ссылки между новыми строками («← сессия») появятся только при записи.
    """
    service, posts = found["service"], found["posts"]
    post = ACTIONS[action]
    work_place = posts.get(post) or {}
    sclad = work_place.get("sclad_id") or service.get("current_sclad_id")
    ts = (now or datetime.now()).isoformat(timespec="milliseconds")
    status = service.get("status_id") or 0
    new_status = STATUS_IN_WORK if action == "in" and status < STATUS_IN_WORK else status
    dep = {"DEP_ID": DEP_ID, "LAST_DEP_ID": DEP_ID, "DEP_SRC_ID": DEP_ID}

    writes: list[dict[str, Any]] = [
        {
            "table": "USER_SESSION", "op": "insert", "label": "Сессия мастера на посту",
            "fields": {"USER_ID": master_user_id, "WORK_PLACE_ID": post,
                       "DATE_BEG": ts, "DATE_END": ts, "DATE_UPD": ts, **dep},
        },
        {
            "table": "USER_SESSION_COWORKS", "op": "insert", "label": "Напарники",
            "fields": {"WORK_PLACE_ID": post, "COWORKERS_CNT": 1,
                       "DOC_ORDER_SERVICES_ID": service["id"], "BARCODE": service.get("barcode"), **dep},
        },
        {
            "table": "USER_SESSION_ACTIONS", "op": "insert", "label": "Действие по бирке",
            "fields": {"USER_SESSION_ID": "← сессия", "DATE_BEG": ts, "DATE_END": ts,
                       "DOC_ORDER_SERVICES_ID": service["id"], "SALARY_KOEF": 1.0,
                       "WORK_PLACE_ID": post, "WP_KOEF": work_place.get("proc") or None,
                       "COWORKERS_CNT": 1, "BARCODE": service.get("barcode"),
                       "COWORK_ID": "← напарники", "LAST_WORK": 1, **dep},
            "note": "NONACTIVE база проставит сама, когда появится история действия.",
        },
        {
            "table": "USER_ACTION_HIST", "op": "insert", "label": "История действий",
            "fields": {"USA_ID": "← действие", "KIND_ID": ACTION_HIST_KIND, "DTTM": ts, **dep},
        },
        {
            "table": "DOC_ORDER_SERVICES", "op": "update", "label": "Услуга",
            "key": {"ID": service["id"]},
            "fields": {"STATUS_ID": new_status, "CURRENT_WORK_PLACE_ID": post, "CURRENT_SCLAD_ID": sclad,
                       "LAST_TIME_CH_STATUS": ts, "LAST_TIME_CH_CUR_SCLAD": ts},
        },
        {
            "table": "DOC_ORDER_SERV_HISTORY", "op": "insert", "label": "История услуги",
            "fields": {"DOS_ID": service["id"], "DT": ts, "USER_ID": master_user_id,
                       "STATUS_ID": new_status, "CURRENT_SCLAD_ID": sclad, "CURRENT_WP_ID": post,
                       "KREDIT": service.get("kredit"), "KFX": service.get("kfx"),
                       "QTY_KREDIT": service.get("qty_kredit"),
                       "LAST_TIME_CH_STATUS": ts, "LAST_TIME_CH_CUR_SCLAD": ts, **dep},
        },
    ]
    if action == "in":
        order_status = service.get("order_status_id") or 0
        new_order_status = STATUS_IN_WORK if order_status < STATUS_IN_WORK else order_status
        writes += [
            {
                "table": "DOCS_ORDER", "op": "update", "label": "Заказ",
                "key": {"ID": service["doc_order_id"]},
                "fields": {"STATUS_ID": new_order_status, "CURRENT_SCLAD_ID": sclad},
                "note": "Дату начала заказа база проставит сама при смене статуса.",
            },
            {
                "table": "DOCS_ORDER_HISTORY", "op": "insert", "label": "История заказа",
                "fields": {"DOC_ORDER_ID": service["doc_order_id"], "STATUS_ID": new_order_status,
                           "USER_ID": master_user_id, "CURRENT_SCLAD_ID": sclad},
                "note": "Набор полей — по наблюдению; уточним на пилоте.",
            },
        ]
    return writes


def _public_service(found: dict[str, Any]) -> dict[str, Any]:
    service, posts = found["service"], found["posts"]
    current = service.get("current_work_place_id")
    return {
        "doc_num": service.get("doc_num"),
        "name": service.get("name"),
        "kredit": service.get("kredit"),
        "barcode": service.get("barcode"),
        "status_id": service.get("status_id"),
        "status_name": STATUS_NAMES.get(service.get("status_id"), "—"),
        "current_post": (posts.get(current) or {}).get("name") if current else None,
    }


def _public_scans(found: dict[str, Any], master_user_id: int) -> list[dict[str, Any]]:
    posts = found["posts"]
    return [
        {
            "date": s["date"],
            "post_id": s["work_place_id"],
            "post_name": (posts.get(s["work_place_id"]) or {}).get("name") or f"Пост {s['work_place_id']}",
            "master": s["master"],
            "is_me": s["user_id"] == master_user_id,
        }
        for s in found["scans"]
    ]


def describe(master, barcode: str) -> Optional[dict[str, Any]]:
    """Что показать мастеру после скана: услуга, её сканы и проверки обоих действий."""
    # Кривой номер отсекаем до поиска: ответ «не похоже на бирку» не должен
    # зависеть от того, как устроен поиск в базе.
    if len(normalize_barcode(barcode)) not in (14, 18):
        raise BarcodeError("invalid_barcode")
    found = lookup(barcode)
    if found is None:
        return None
    return {
        "dry_run": True,
        "service": _public_service(found),
        "scans": _public_scans(found, master.agbis_user_id),
        "suggested_action": suggest_action(found),
        "checks": {name: check(found, name, master.agbis_user_id) for name in ACTIONS},
    }


def plan(master, barcode: str, action: str, now: Optional[datetime] = None) -> Optional[dict[str, Any]]:
    """Подтверждённый мастером скан в пробном режиме: проверки и план записи.

    В Агбис не пишется ничего. План строится, только если скан разрешён, —
    незачем показывать строки, которые всё равно не будут записаны.
    """
    if action not in ACTIONS:
        raise ValueError("invalid_action")
    # Кривой номер отсекаем до поиска: ответ «не похоже на бирку» не должен
    # зависеть от того, как устроен поиск в базе.
    if len(normalize_barcode(barcode)) not in (14, 18):
        raise BarcodeError("invalid_barcode")
    found = lookup(barcode)
    if found is None:
        return None
    result = check(found, action, master.agbis_user_id)
    post = found["posts"].get(ACTIONS[action]) or {"id": ACTIONS[action], "name": None}
    return {
        "dry_run": True,
        "action": action,
        "post": {"id": post["id"], "name": post.get("name")},
        "service": _public_service(found),
        **result,
        "writes": plan_writes(found, action, master.agbis_user_id, now) if result["allowed"] else [],
    }
