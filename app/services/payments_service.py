"""Оплаты за период: деньги, которые пришли, с разбивкой по видам оплаты.

Не выручка (сумма оказанных услуг), а сами платежи клиентов: предоплата при
приёме, доплата при выдаче, оплата товара. Источник — DOC_ORDER_PAYS: связь
заказа с документом оплаты; сумма платежей по заказу сходится с
DOCS_ORDER.DEBET (сверено на 300 заказах за месяц). Кассовая книга
DOCS_KASSA для этого не годится — в ней только наличные.

Вид оплаты — DOC_ORDER_PAYS.DOC_TYPE (справочник DOC_TYPES). Деньгами
считаем карту, наличные и безнал по счёту; бонусы и депозит — это списание
ранее начисленного, а не поступление денег, их показываем отдельно.
Возврат — KREDIT документа оплаты, вычитается из того же вида.

Точка — подразделение документа оплаты (DOCS.DEP_SRC_ID, справочник DEPS):
где деньги приняли, а не где принят заказ.
"""
from __future__ import annotations

from datetime import date
from typing import Any

# doc_type → (ключ, подпись, деньги ли это)
KINDS: dict[int, tuple[str, str, bool]] = {
    9: ("card", "Картой", True),
    31: ("cash", "Наличными", True),
    # Кассовый документ через центральную кассу «Основная»: предоплаты и
    # их возвраты, оформленные не на точке. Это тоже наличные деньги.
    3: ("cash", "Наличными", True),
    4: ("bank", "Безнал по счёту", True),
    91: ("bonus", "Бонусами", False),
    92: ("deposit", "С депозита", False),
}
KIND_ORDER = ["card", "cash", "bank", "bonus", "deposit", "other"]
KIND_LABELS = {k: label for k, label, _ in KINDS.values()} | {"other": "Другое"}
MONEY_KINDS = {"card", "cash", "bank", "other"}

# DEPS: салоны. «Пассаж» в Агбисе так и не переименовали в Гранд Палас.
POINT_NAMES = {3: "Озерки", 5: "Академическая", 7: "Гранд Палас", 8: "Бестужевская",
               11: "Меркурий", 17: "Охта Молл"}
OTHER_POINT = "Офис / другое"


def payments(date_from: date, date_to: date) -> dict[str, Any]:
    from app.services.firebird_service import _connect

    con = _connect()
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT p.doc_type, d.dep_src_id, COUNT(*), SUM(d.debet), SUM(d.kredit), d.doc_date "
            "FROM doc_order_pays p JOIN docs d ON d.doc_id = p.doc_id "
            "WHERE d.doc_date BETWEEN ? AND ? GROUP BY p.doc_type, d.dep_src_id, d.doc_date",
            (date_from, date_to))
        rows = cur.fetchall()
    finally:
        con.close()

    kinds: dict[str, dict[str, Any]] = {}
    points: dict[str, dict[str, Any]] = {}
    days: dict[str, dict[str, Any]] = {}
    for doc_type, dep, count, debet, kredit, doc_date in rows:
        key = KINDS.get(doc_type, ("other", "Другое", True))[0]
        income, refund = round(float(debet or 0), 2), round(float(kredit or 0), 2)
        k = kinds.setdefault(key, {"key": key, "label": KIND_LABELS[key], "money": key in MONEY_KINDS,
                                   "amount": 0.0, "refunds": 0.0, "count": 0})
        # amount — сколько пришло этим видом оплаты (без вычета возвратов):
        # возвраты показываем отдельной строкой, чтобы их было видно.
        k["amount"] += income
        k["refunds"] += refund
        k["count"] += int(count or 0)
        day = doc_date.isoformat() if hasattr(doc_date, "isoformat") else str(doc_date)
        dd = days.setdefault(day, {"date": day, "money": 0.0, "card": 0.0, "cash": 0.0, "bank": 0.0,
                                   "other": 0.0, "bonus": 0.0, "deposit": 0.0, "refunds": 0.0})
        if key not in MONEY_KINDS:
            dd[key] += income
            continue
        dd[key] += income
        dd["refunds"] += refund
        dd["money"] += income - refund
        name = POINT_NAMES.get(dep, OTHER_POINT)
        pt = points.setdefault(name, {"name": name, "money": 0.0, "card": 0.0, "cash": 0.0, "bank": 0.0,
                                      "other": 0.0, "refunds": 0.0})
        pt[key] += income
        pt["refunds"] += refund
        pt["money"] += income - refund

    kind_list = sorted(kinds.values(), key=lambda k: KIND_ORDER.index(k["key"]))
    for k in kind_list:
        k["amount"] = round(k["amount"], 2)
        k["refunds"] = round(k["refunds"], 2)
    point_list = sorted(points.values(), key=lambda p: (p["name"] == OTHER_POINT, -p["money"]))
    for p in point_list:
        for f in ("money", "card", "cash", "bank", "other", "refunds"):
            p[f] = round(p[f], 2)
    day_list = sorted(days.values(), key=lambda d: d["date"], reverse=True)
    for d in day_list:
        for f in list(d):
            if f != "date":
                d[f] = round(d[f], 2)
    money = [k for k in kind_list if k["money"]]
    received = round(sum(k["amount"] for k in money), 2)
    refunds = round(sum(k["refunds"] for k in money), 2)
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        # Пришло деньгами (наличные, карта, безнал) — до возвратов.
        "received": received,
        "refunds": refunds,
        # Чистый плюс: пришло деньгами минус возвраты. Бонусы и депозит
        # сюда не входят — это не деньги.
        "net": round(received - refunds, 2),
        "total": round(received - refunds, 2),
        "count": sum(k["count"] for k in money),
        "kinds": kind_list,
        "points": point_list,
        "days": day_list,
    }
