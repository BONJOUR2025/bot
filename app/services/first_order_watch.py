"""Сторож первого заказа, сданного в «Чистомат».

Три вещи, которые выяснились при разборе и определили устройство:

1. **Чистомат — это склад, а не подразделение.** `SCLADS.id=10125`,
   название «Чистомат 1». Поиск идёт по названию, а не по номеру: точку
   могут пересоздать или добавить «Чистомат 2», и тогда сторож подхватит
   её сам.

2. **Заказ привязывается к складу приёмки через `sclad_kredit_id`.**
   Проверено на живых данных: у заказа 1232305 `kredit=21021`
   (Бестужевская), а `current_sclad_id=10125` — то есть он принят на
   Бестужевской и лишь перемещён в Чистомат. Считать такой сданным в
   чистомат было бы неверно.

3. **На складе уже есть 19 заказов от 3–22 июня** (номера 00003–00019,
   плотно за четыре дня, потом два месяца тишины) — очевидно тестовые.
   Поэтому «первый заказ» отсчитывается не от начала времён, а от момента
   установки сторожа: при первом запуске он запоминает последний
   существующий заказ и ждёт следующего за ним.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Подстрока названия склада, регистр не важен.
WATCH_NAMES = ("чистомат",)

CFG_BASELINE = "first_order_baseline"  # {"чистомат": 123456}  — doc_id на момент установки
CFG_SEEN = "first_order_seen"          # {"чистомат": "00020"} — уже поздравили


def _dict(cfg: dict, key: str) -> dict:
    raw = cfg.get(key) or {}
    return raw if isinstance(raw, dict) else {}


def _sclad_ids(cur, name_part: str) -> dict[int, str]:
    cur.execute("SELECT id, name FROM sclads WHERE UPPER(name) LIKE UPPER(?)", (f"%{name_part}%",))
    out = {}
    for row in cur.fetchall():
        name = row[1].decode("utf-8", "replace") if isinstance(row[1], bytes) else (row[1] or "")
        out[row[0]] = name.strip()
    return out


def latest_doc_id(name_part: str) -> int | None:
    """Самый свежий заказ склада — точка отсчёта. None, если склада нет."""
    from app.services.firebird_service import FIREBIRD_AVAILABLE, _connect

    if not FIREBIRD_AVAILABLE:
        return None
    con = _connect()
    try:
        cur = con.cursor()
        sclads = _sclad_ids(cur, name_part)
        if not sclads:
            return None
        ids = ",".join(str(i) for i in sclads)
        cur.execute(f"SELECT MAX(o.doc_id) FROM docs_order o WHERE o.sclad_kredit_id IN ({ids})")
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        con.close()


def find_order_after(name_part: str, after_doc_id: int) -> dict | None:
    """Первый заказ, сданный в этот склад ПОСЛЕ указанного doc_id."""
    from app.services.firebird_service import FIREBIRD_AVAILABLE, _connect

    if not FIREBIRD_AVAILABLE:
        return None
    con = _connect()
    try:
        cur = con.cursor()
        sclads = _sclad_ids(cur, name_part)
        if not sclads:
            return None
        ids = ",".join(str(i) for i in sclads)
        cur.execute(
            f"""
            SELECT FIRST 1 d.doc_num, d.doc_date, o.sclad_kredit_id, o.doc_id
            FROM docs_order o
                INNER JOIN docs d ON d.doc_id = o.doc_id
            WHERE o.sclad_kredit_id IN ({ids}) AND o.doc_id > ?
            ORDER BY o.doc_id
            """,
            (after_doc_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "doc_num": str(row[0]),
            "doc_date": row[1],
            "sclad_name": sclads.get(row[2], name_part),
            "doc_id": int(row[3]),
        }
    finally:
        con.close()


def _celebration(order: dict) -> str:
    # docs.doc_date хранит только дату, поэтому «в 00:00» было бы враньём —
    # показываем время лишь тогда, когда оно действительно есть.
    d = order.get("doc_date")
    if not d:
        when = "только что"
    elif getattr(d, "hour", 0) or getattr(d, "minute", 0):
        when = d.strftime("%d.%m.%Y в %H:%M")
    else:
        when = d.strftime("%d.%m.%Y")
    return (
        "🎉🎉🎉\n\n"
        f"<b>ПЕРВЫЙ ЗАКАЗ В «{order['sclad_name'].upper()}»!</b>\n\n"
        "🥳 Свершилось! Чистомат принял своего первого клиента.\n\n"
        f"📄 Заказ <b>{order['doc_num']}</b>\n"
        f"🕒 {when}\n\n"
        "Поздравляю! 🍾✨🎊"
    )


async def check_and_notify() -> bool:
    """Проверить и поздравить, если пора. True — если уведомление ушло."""
    from app.services.config_service import ConfigService
    from app.services.notify import send_notification

    svc = ConfigService()
    cfg = svc.load()
    baseline = _dict(cfg, CFG_BASELINE)
    seen = _dict(cfg, CFG_SEEN)
    fired = False

    for name_part in WATCH_NAMES:
        if seen.get(name_part):
            continue
        try:
            if name_part not in baseline:
                # Первый запуск: запоминаем, что уже есть, и ждём следующего.
                # Без этого поздравление ушло бы за июньские тестовые заказы.
                last = latest_doc_id(name_part)
                if last is None:
                    continue  # склада ещё нет
                baseline[name_part] = last
                svc.patch({CFG_BASELINE: baseline})
                log.info("first_order_watch: точка отсчёта для «%s» — doc_id=%s", name_part, last)
                continue

            order = find_order_after(name_part, int(baseline[name_part]))
        except Exception as exc:
            log.warning("first_order_watch: не удалось проверить «%s»: %s", name_part, exc)
            continue
        if not order:
            continue

        # Пишем в конфиг ДО отправки: если Telegram не ответит, лучше
        # промолчать один раз, чем поздравлять на каждом цикле проверки.
        seen[name_part] = order["doc_num"]
        svc.patch({CFG_SEEN: seen})
        log.info("first_order_watch: первый заказ в «%s» — %s", order["sclad_name"], order["doc_num"])

        await send_notification(_celebration(order))
        fired = True

    return fired
