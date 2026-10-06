"""Оплата заказа клиентом — плашка «Не оплачен / Предоплата N ₽ / Оплачен»
в приложении мастера, у старшего мастера и в «Цехе» админки.

Источник — DOCS_ORDER: KREDIT (сколько клиент должен за заказ) и DEBET
(сколько уже внёс). Считаем по суммам, а не по PAY_STATUS_ID: в Агбисе
встречаются заказы со статусом «Оплачен полностью» и недоплатой — флаг
отстаёт от денег (см. firebird_service.get_receivables).

Мастеру это нужно, чтобы не отдавать неоплаченное и знать, сколько
дооплатить при выдаче.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

log = logging.getLogger(__name__)

_CHUNK = 500  # Firebird ограничивает IN (…) 1500 элементами


def payment(kredit: Any, debet: Any) -> dict[str, Any]:
    """{"state": "unpaid" | "prepaid" | "paid", "paid", "total", "left"}."""
    total = round(float(kredit or 0), 2)
    paid = round(float(debet or 0), 2)
    if paid <= 0 and total > 0:
        state = "unpaid"
    elif paid + 0.5 < total:
        state = "prepaid"
    else:
        state = "paid"
    return {"state": state, "paid": paid, "total": total, "left": round(max(total - paid, 0), 2)}


def by_doc_nums(doc_nums: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """Оплата по номерам заказов одним-двумя запросами к Агбису."""
    from app.services.firebird_service import _connect

    nums = sorted({str(n).strip() for n in doc_nums if n})
    out: dict[str, dict[str, Any]] = {}
    if not nums:
        return out
    con = _connect()
    try:
        cur = con.cursor()
        for i in range(0, len(nums), _CHUNK):
            part = nums[i:i + _CHUNK]
            cur.execute(
                "SELECT d.doc_num, dor.kredit, dor.debet FROM docs_order dor "
                "JOIN docs d ON d.doc_id = dor.doc_id "
                f"WHERE d.doc_num IN ({','.join('?' * len(part))})", part)
            for doc_num, kredit, debet in cur.fetchall():
                out[str(doc_num).strip()] = payment(kredit, debet)
    finally:
        con.close()
    return out


def _walk(obj: Any, found: list[dict]) -> None:
    if isinstance(obj, dict):
        if obj.get("doc_num"):
            found.append(obj)
        for v in obj.values():
            _walk(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, found)


def attach(obj: Any) -> Any:
    """Проставить "payment" каждому словарю с "doc_num" внутри obj (списки
    «Цеха», «В работе», карточка заказа). Ошибка Агбиса не роняет экран —
    плашки просто не будет."""
    found: list[dict] = []
    _walk(obj, found)
    if not found:
        return obj
    try:
        pays = by_doc_nums(d["doc_num"] for d in found)
    except Exception:
        log.warning("order_payment: оплата заказов не получена", exc_info=True)
        return obj
    for d in found:
        p = pays.get(str(d["doc_num"]).strip())
        if p:
            d["payment"] = p
    return obj
