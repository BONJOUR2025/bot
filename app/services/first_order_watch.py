"""Сторож первого заказа с новой точки.

Заведён под «Чистомат» — точку самообслуживания, которой в Agbis ещё нет.
Отсюда главное решение: ищем по НАЗВАНИЮ подразделения, а не по его номеру.
Номер появится только вместе с точкой, и просить его заранее — значит
вернуться к этой задаче ещё раз; название же известно сейчас, и сторож
сработает сам в тот день, когда точку заведут.

Срабатывает один раз: факт и номер заказа записываются в конфиг, дальше
проверка выходит сразу. Это важнее, чем кажется, — «первый заказ» бывает
один, и повторное поздравление обесценило бы его.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Подстрока названия подразделения, регистр не важен. Список, потому что
# точку могут назвать «Чистомат», «ЧистоМат №1» или «Чистомат Озерки».
WATCH_NAMES = ("чистомат",)

CFG_SEEN = "first_order_seen"  # {"чистомат": "64863-5"}


def _seen(cfg: dict) -> dict:
    raw = cfg.get(CFG_SEEN) or {}
    return raw if isinstance(raw, dict) else {}


def find_first_order(name_part: str) -> dict | None:
    """Самый ранний заказ, созданный на точке с таким названием.

    None — если такой точки ещё нет или заказов на ней не было. Оба случая
    штатные: до открытия точки их не будет каждый раз.
    """
    from app.services.firebird_service import FIREBIRD_AVAILABLE, _connect

    if not FIREBIRD_AVAILABLE:
        return None

    con = _connect()
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT dep_id, name FROM deps WHERE UPPER(name) LIKE UPPER(?)",
            (f"%{name_part}%",),
        )
        deps = []
        for row in cur.fetchall():
            dep_name = row[1].decode("utf-8", "replace") if isinstance(row[1], bytes) else (row[1] or "")
            deps.append((row[0], dep_name.strip()))
        if not deps:
            return None

        ids = ",".join(str(d[0]) for d in deps)
        # FIRST 1 + ORDER BY: нужен именно первый заказ, а не любой.
        cur.execute(
            f"""
            SELECT FIRST 1 d.doc_num, d.doc_date, d.dep_src_id
            FROM docs d
            WHERE d.dep_src_id IN ({ids})
            ORDER BY d.doc_date, d.doc_id
            """
        )
        row = cur.fetchone()
        if not row:
            return None
        by_id = dict(deps)
        return {
            "doc_num": str(row[0]),
            "doc_date": row[1],
            "dep_id": row[2],
            "dep_name": by_id.get(row[2], name_part),
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
        f"<b>ПЕРВЫЙ ЗАКАЗ В «{order['dep_name'].upper()}»!</b>\n\n"
        "🥳 Это случилось! Точка заработала и приняла своего первого клиента.\n\n"
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
    seen = _seen(cfg)
    fired = False

    for name_part in WATCH_NAMES:
        if seen.get(name_part):
            continue
        try:
            order = find_first_order(name_part)
        except Exception as exc:
            log.warning("first_order_watch: не удалось проверить «%s»: %s", name_part, exc)
            continue
        if not order:
            continue

        # Пишем в конфиг ДО отправки: если Telegram не ответит, лучше
        # промолчать один раз, чем поздравлять с первым заказом на каждом
        # цикле проверки.
        seen[name_part] = order["doc_num"]
        svc.patch({CFG_SEEN: seen})
        log.info("first_order_watch: первый заказ в «%s» — %s", order["dep_name"], order["doc_num"])

        await send_notification(_celebration(order))
        fired = True

    return fired
