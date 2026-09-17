"""Вход и выход по услугам из приложения мастера.

Мастер сканирует бирку, видит услугу и проверки, подтверждает — и скан
пишется в Агбис так же, как его пишет терминал цеха (AgentNG). Запись
включается флагом AGBIS_SCAN_WRITE в .env; без него модуль работает в
пробном режиме и только показывает план записи.

Как устроен штатный скан, восстановлено контролируемым опытом 17.09.2026 на
тестовом заказе 32306-21 (снимки базы до и после каждого скана):

- мастер «стоит» на посту: у него открытая смена (USER_SESSION без
  DATE_END), каждая бирка — отметка в ней, а не новая смена;
- одна отметка — это отметка, напарники, история действия и история услуги;
  услуга получает пост, на входе — ещё статус «в исполнении»;
- номера строк (код базы + счётчик), коды подразделений, журнал обмена между
  базами и дату начала услуги ставят триггеры базы — руками их не пишем;
- повтор на том же посту триггер базы засчитывает переделкой и помечает
  прошлую работу браком, а терминал ещё просит комментарий и пишет возврат
  изделия. Этого приложение не повторяет: повтор здесь запрещён, его делают
  на терминале;
- процент поста (WP_KOEF: 0 на входе, 23 на выходе) — настройка поста, не
  зарплата; зарплату считает masters_service по категории услуги.
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

# USER_ACTION_HIST.KIND_ID у скана на посту.
ACTION_HIST_KIND = 3

BARCODE_ERRORS = {
    "invalid_barcode": "Не похоже на номер бирки: нужно 18 цифр (или 14 последних).",
    "ambiguous_barcode": "По этому номеру нашлось несколько услуг — отсканируйте полный штрихкод.",
}

_SERVICE_COLUMNS = (
    "id", "doc_order_id", "status_id", "current_work_place_id", "current_sclad_id",
    "kredit", "kfx", "qty_kredit", "barcode", "name", "doc_num",
    "order_status_id", "order_current_sclad_id", "folder_id", "top_category",
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
                dor.status_id, dor.current_sclad_id, t.folder_id, top.name
            FROM doc_order_services dos
                JOIN docs_order dor ON dor.id = dos.doc_order_id
                JOIN docs d ON d.doc_id = dor.doc_id
                LEFT JOIN tovars_tbl t ON t.tovar_id = dos.tovar_id
                LEFT JOIN tree folder ON folder.folder_id = t.folder_id
                LEFT JOIN tree top ON top.folder_id = folder.top_parent
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
        blockers.append(
            f"{what} уже был {_fmt_dt(last['date'])} ({who}). Повтор — это переделка: "
            "отметьте его на терминале цеха, там он запросит комментарий."
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


def write_enabled() -> bool:
    """Включена ли настоящая запись в Агбис (AGBIS_SCAN_WRITE в .env)."""
    from app.settings import settings

    return bool(getattr(settings, "agbis_scan_write", False))


def plan_writes(
    found: dict[str, Any], action: str, master_user_id: int, now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Строки, которые пишет скан, — ровно как терминал цеха (AgentNG).

    Сверено с настоящими сканами 17.09.2026 на тестовом заказе 32306-21:
    отметка ложится в ОТКРЫТУЮ смену мастера на посту (новая смена — только
    если открытой нет), к ней строка напарников, история действия и история
    услуги; услуга получает пост и время смены статуса, на входе — ещё статус
    «в исполнении». Заказ терминал не трогает: его статус пересчитывает
    SP_GET_ORDER_STATUS, и только если статус услуги поменялся.

    Номера строк, коды подразделений, журнал обмена между базами, дата начала
    услуги и пометка переделки — дело триггеров базы, сюда они не входят.
    Ссылки между строками («← смена») появляются при записи.
    """
    service, posts = found["service"], found["posts"]
    post = ACTIONS[action]
    work_place = posts.get(post) or {}
    ts = (now or datetime.now()).isoformat(timespec="milliseconds")
    status = service.get("status_id") or 0
    new_status = STATUS_IN_WORK if action == "in" and status < STATUS_IN_WORK else status
    post_name = work_place.get("name") or str(post)

    writes: list[dict[str, Any]] = [
        {
            "table": "USER_SESSION", "op": "upsert", "label": "Смена мастера на посту",
            "fields": {"USER_ID": master_user_id, "WORK_PLACE_ID": post, "DATE_UPD": ts},
            "note": "Открытая смена мастера на этом посту; если её нет — новая, с началом в момент скана.",
        },
        {
            "table": "USER_SESSION_COWORKS", "op": "insert", "label": "Напарники",
            "fields": {"WORK_PLACE_ID": post, "COWORKERS_CNT": 1,
                       "DOC_ORDER_SERVICES_ID": service["id"], "BARCODE": service.get("barcode")},
        },
        {
            "table": "USER_SESSION_ACTIONS", "op": "insert", "label": "Отметка по бирке",
            "fields": {"USER_SESSION_ID": "← смена", "DATE_BEG": ts, "DATE_END": ts,
                       "DOC_ORDER_SERVICES_ID": service["id"], "REEXECUTION": 0, "SALARY_KOEF": 1.0,
                       "WORK_PLACE_ID": post, "WP_KOEF": work_place.get("proc") or 0.0,
                       "COWORKERS_CNT": 1, "NONACTIVE": 1, "BARCODE": service.get("barcode"),
                       "COWORK_ID": "← напарники", "BAD_WORK": 0, "BAD_LOOK": 0, "LAST_WORK": 1,
                       "QTY": 0.0, "ITERATION_LEVEL": 0, "FITTING": 0, "IS_ADD_OUT_OF_SERVICES": 0},
        },
        {
            "table": "USER_ACTION_HIST", "op": "insert", "label": "История действия",
            "fields": {"USA_ID": "← отметка", "KIND_ID": ACTION_HIST_KIND, "DTTM": ts},
        },
        {
            "table": "DOC_ORDER_SERVICES", "op": "update", "label": "Услуга",
            "key": {"ID": service["id"]},
            "fields": {"STATUS_ID": new_status, "CURRENT_WORK_PLACE_ID": post,
                       "LAST_TIME_CH_STATUS": ts, "LAST_TIME_CH_CUR_SCLAD": ts},
        },
        {
            "table": "DOC_ORDER_SERV_HISTORY", "op": "insert", "label": "История услуги",
            "fields": {"DOS_ID": service["id"], "DT": ts, "USER_ID": master_user_id,
                       "STATUS_ID": new_status, "CURRENT_SCLAD_ID": service.get("current_sclad_id"),
                       "CURRENT_WP_ID": post, "KREDIT": service.get("kredit"), "KFX": service.get("kfx"),
                       "QTY_KREDIT": service.get("qty_kredit"), "BASIS": _history_basis(post_name),
                       "LAST_TIME_CH_STATUS": ts, "LAST_TIME_CH_CUR_SCLAD": ts},
        },
    ]
    if new_status != status:
        writes.append({
            "table": "DOCS_ORDER", "op": "update", "label": "Заказ",
            "key": {"ID": service["doc_order_id"]},
            "fields": {"STATUS_ID": "по SP_GET_ORDER_STATUS"},
            "note": "Только если процедура Агбиса скажет, что статус заказа меняется; тогда же строка истории заказа.",
        })
    return writes


def _history_basis(post_name: str) -> str:
    return f"Изменение статуса услуги на рабочем месте {post_name} из приложения мастера"


class ScanRejected(RuntimeError):
    """Перед самой записью проверка не прошла — например, бирку успели отсканировать на терминале."""


def execute_writes(con, found: dict[str, Any], action: str, master_user_id: int,
                   now: Optional[datetime] = None) -> dict[str, Any]:
    """Записывает скан в Агбис одной транзакцией и возвращает номера новых строк.

    Строку услуги блокируем и перечитываем внутри транзакции: между показом
    мастеру и подтверждением бирку мог отсканировать терминал, и наша отметка
    стала бы переделкой (а переделку триггер базы засчитывает браком прошлой
    работы). При любой ошибке — откат целиком, в Агбисе не остаётся полускана.
    """
    service, posts = found["service"], found["posts"]
    post = ACTIONS[action]
    work_place = posts.get(post) or {}
    ts = now or datetime.now()
    cur = con.cursor()
    try:
        cur.execute(
            "SELECT status_id, current_sclad_id, kredit, kfx, qty_kredit, doc_order_id, barcode "
            "FROM doc_order_services WHERE id = ? WITH LOCK",
            (service["id"],),
        )
        rows = cur.fetchall()
        if not rows:
            raise ScanRejected("Услуга не найдена в Агбисе.")
        status, sclad, kredit, kfx, qty, order_id, barcode = rows[0]
        status = status or 0
        if status in CLOSED_STATUSES:
            raise ScanRejected(f"Услуга уже в статусе «{STATUS_NAMES.get(status, status)}».")
        cur.execute(
            "SELECT work_place_id FROM user_session_actions WHERE doc_order_services_id = ?",
            (service["id"],),
        )
        done_posts = {r[0] for r in cur.fetchall()}
        if post in done_posts:
            raise ScanRejected("По этой бирке такая отметка уже есть — повтор отмечается на терминале цеха.")
        if action == "out" and not done_posts.intersection(POSTS_BEFORE_OUT):
            raise ScanRejected("Входа в цех по этой бирке не было — сначала отсканируйте вход.")

        new_status = STATUS_IN_WORK if action == "in" and status < STATUS_IN_WORK else status

        cur.execute(
            "SELECT FIRST 1 id FROM user_session "
            "WHERE user_id = ? AND work_place_id = ? AND date_end IS NULL ORDER BY date_beg DESC",
            (master_user_id, post),
        )
        open_session = cur.fetchall()
        if open_session:
            session_id = open_session[0][0]
            cur.execute("UPDATE user_session SET date_upd = ? WHERE id = ?", (ts, session_id))
        else:
            cur.execute(
                "INSERT INTO user_session (user_id, work_place_id, date_beg, date_upd) "
                "VALUES (?, ?, ?, ?) RETURNING id",
                (master_user_id, post, ts, ts),
            )
            session_id = cur.fetchall()[0][0]

        cur.execute(
            "INSERT INTO user_session_coworks (work_place_id, coworkers_cnt, doc_order_services_id, barcode) "
            "VALUES (?, 1, ?, ?) RETURNING id",
            (post, service["id"], barcode),
        )
        cowork_id = cur.fetchall()[0][0]

        cur.execute(
            "INSERT INTO user_session_actions (user_session_id, date_beg, date_end, doc_order_services_id, "
            "reexecution, salary_koef, work_place_id, wp_koef, coworkers_cnt, nonactive, barcode, cowork_id, "
            "bad_work, bad_look, last_work, qty, iteration_level, fitting, is_add_out_of_services) "
            "VALUES (?, ?, ?, ?, 0, 1, ?, ?, 1, 1, ?, ?, 0, 0, 1, 0, 0, 0, 0) RETURNING id",
            (session_id, ts, ts, service["id"], post, work_place.get("proc") or 0.0, barcode, cowork_id),
        )
        action_id = cur.fetchall()[0][0]

        cur.execute(
            "INSERT INTO user_action_hist (usa_id, kind_id, dttm) VALUES (?, ?, ?)",
            (action_id, ACTION_HIST_KIND, ts),
        )
        cur.execute(
            "UPDATE doc_order_services SET status_id = ?, current_work_place_id = ?, "
            "last_time_ch_status = ?, last_time_ch_cur_sclad = ? WHERE id = ?",
            (new_status, post, ts, ts, service["id"]),
        )
        cur.execute(
            "INSERT INTO doc_order_serv_history (dos_id, dt, user_id, status_id, current_sclad_id, current_wp_id, "
            "kredit, kfx, qty_kredit, basis, last_time_ch_status, last_time_ch_cur_sclad) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (service["id"], ts, master_user_id, new_status, sclad, post, kredit, kfx, qty,
             # BASIS здесь — двоичный BLOB, клиент Агбиса кладёт в него текст в cp1251.
             _history_basis(work_place.get("name") or str(post)).encode("cp1251", "replace"), ts, ts),
        )

        order_status = None
        if new_status != status:
            cur.execute("SELECT status_id, is_change FROM sp_get_order_status(?, 0)", (order_id,))
            sp = cur.fetchall()
            if sp and sp[0][1] == 1:
                order_status = sp[0][0]
                cur.execute(
                    "UPDATE docs_order SET status_id = ?, date_order_start = COALESCE(date_order_start, ?) "
                    "WHERE id = ?",
                    (order_status, ts, order_id),
                )
                cur.execute(
                    "INSERT INTO docs_order_history (doc_order_id, debet, kredit, status_id, pay_status_id, "
                    "date_out, doc_date, doc_time, basis, operation, discount, user_id, current_sclad_id) "
                    "SELECT dor.id, dor.debet, dor.kredit, dor.status_id, dor.pay_status_id, dor.date_out, "
                    "CAST(? AS DATE), CAST(? AS TIME), ?, 2, dor.discount, ?, dor.current_sclad_id "
                    "FROM docs_order dor WHERE dor.id = ?",
                    (ts, ts, "Изменение статуса заказа по скану в приложении мастера", master_user_id, order_id),
                )
        con.commit()
    except Exception:
        con.rollback()
        raise
    return {"session_id": session_id, "action_id": action_id, "cowork_id": cowork_id,
            "service_status_id": new_status, "order_status_id": order_status}


def earning(found: dict[str, Any], master) -> Optional[dict[str, Any]]:
    """Сколько мастер заработает на выходе по этой услуге — по правилам отчёта.

    Та же формула, что masters_service: цена услуги × ставка по верхней
    категории (23% химчистка и реставрация, 20% остальное), и только для папок,
    за которые зарплата вообще начисляется. None — услуга не оплачивается
    сдельно (например, «Изделие»). У ученика сумма справочная: на руки идёт
    стипендия.
    """
    from app.services.masters_service import SALARY_FOLDER_IDS, _salary_rate

    service = found["service"]
    if service.get("folder_id") not in SALARY_FOLDER_IDS:
        return None
    rate = _salary_rate(service.get("top_category"))
    kredit = service.get("kredit") or 0.0
    return {
        "kredit": kredit,
        "rate": rate,
        "salary": round(kredit * rate, 2),
        "reference_only": bool(getattr(master, "is_apprentice", False)),
    }


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
        "dry_run": not write_enabled(),
        "service": _public_service(found),
        "scans": _public_scans(found, master.agbis_user_id),
        "suggested_action": suggest_action(found),
        "checks": {name: check(found, name, master.agbis_user_id) for name in ACTIONS},
    }


def _prepare(master, barcode: str, action: str) -> Optional[tuple[dict[str, Any], dict[str, Any]]]:
    if action not in ACTIONS:
        raise ValueError("invalid_action")
    # Кривой номер отсекаем до поиска: ответ «не похоже на бирку» не должен
    # зависеть от того, как устроен поиск в базе.
    if len(normalize_barcode(barcode)) not in (14, 18):
        raise BarcodeError("invalid_barcode")
    found = lookup(barcode)
    if found is None:
        return None
    return found, check(found, action, master.agbis_user_id)


def _summary(found: dict[str, Any], action: str, result: dict[str, Any]) -> dict[str, Any]:
    post = found["posts"].get(ACTIONS[action]) or {"id": ACTIONS[action], "name": None}
    return {
        "action": action,
        "post": {"id": post["id"], "name": post.get("name")},
        "service": _public_service(found),
        **result,
    }


def plan(master, barcode: str, action: str, now: Optional[datetime] = None) -> Optional[dict[str, Any]]:
    """Скан в пробном режиме: проверки и план записи, в Агбис не пишется ничего.

    План строится, только если скан разрешён, — незачем показывать строки,
    которые всё равно не будут записаны.
    """
    prepared = _prepare(master, barcode, action)
    if prepared is None:
        return None
    found, result = prepared
    return {
        "dry_run": True,
        **_summary(found, action, result),
        "earning": earning(found, master) if action == "out" else None,
        "writes": plan_writes(found, action, master.agbis_user_id, now) if result["allowed"] else [],
    }


def confirm(master, barcode: str, action: str, connect: Optional[Callable[[], Any]] = None,
            now: Optional[datetime] = None) -> Optional[dict[str, Any]]:
    """Подтверждённый мастером скан. С включённой записью — пишет в Агбис.

    Без флага AGBIS_SCAN_WRITE ведёт себя как plan(). Если проверки не прошли
    (здесь или повторно внутри транзакции), в Агбис не пишется ничего, а
    мастер получает причину в blockers.
    """
    if not write_enabled():
        return plan(master, barcode, action, now)
    prepared = _prepare(master, barcode, action)
    if prepared is None:
        return None
    found, result = prepared
    summary = {
        "dry_run": False, **_summary(found, action, result), "written": False, "writes": [],
        "earning": earning(found, master) if action == "out" else None,
    }
    if not result["allowed"]:
        return summary
    if connect is None:
        from app.services.firebird_service import _connect as connect
    con = connect()
    try:
        ids = execute_writes(con, found, action, master.agbis_user_id, now)
    except ScanRejected as exc:
        return {**summary, "allowed": False, "blockers": [str(exc)]}
    finally:
        try:
            con.close()
        except Exception:
            pass
    return {**summary, "written": True, "ids": ids}
