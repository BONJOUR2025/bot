"""Sale transfers — manual corrections that move an order's sale between
employees, layered on top of the read-only Firebird data.

Stored in SQLite (hr.db). Used both by the admin API (CRUD) and by
PayrollService (read, to apply during calculation in the bot and the web).
"""
from __future__ import annotations

import json
import logging

from app.db.session import SessionLocal
from app.models.sale_transfer import SaleTransfer

logger = logging.getLogger(__name__)

CATEGORIES = ("repair", "cosmetics", "shoes")


def list_transfers(month_key: str | None = None) -> list[dict]:
    db = SessionLocal()
    try:
        query = db.query(SaleTransfer)
        if month_key:
            query = query.filter(SaleTransfer.month_key == month_key)
        rows = query.order_by(SaleTransfer.created_at.desc()).all()
        return [t.to_dict() for t in rows]
    finally:
        db.close()


def create_transfer(
    *,
    month_key: str,
    doc_num: str,
    from_category: str,
    to_category: str,
    amount: float,
    from_code: str,
    to_code: str,
    from_name: str = "",
    to_name: str = "",
    order_date: str = "",
    shoes_orders: list | None = None,
    author: str = "",
) -> dict:
    if from_category not in CATEGORIES or to_category not in CATEGORIES:
        raise ValueError("invalid_category")
    if not from_code or not to_code:
        raise ValueError("missing_employee")
    if from_code == to_code and from_category == to_category:
        raise ValueError("no_op")

    db = SessionLocal()
    try:
        exists = (
            db.query(SaleTransfer)
            .filter(
                SaleTransfer.month_key == month_key,
                SaleTransfer.doc_num == str(doc_num),
                SaleTransfer.category == from_category,
                SaleTransfer.to_category == to_category,
            )
            .first()
        )
        if exists:
            raise ValueError("transfer_exists")

        transfer = SaleTransfer(
            month_key=month_key,
            doc_num=str(doc_num),
            category=from_category,
            to_category=to_category,
            amount=float(amount or 0),
            from_code=from_code,
            to_code=to_code,
            from_name=from_name or "",
            to_name=to_name or "",
            order_date=order_date or "",
            shoes_orders=json.dumps(shoes_orders or [], ensure_ascii=False),
            author=author or "",
        )
        db.add(transfer)
        db.commit()
        db.refresh(transfer)
        return transfer.to_dict()
    finally:
        db.close()


def delete_transfer(transfer_id: int) -> bool:
    db = SessionLocal()
    try:
        transfer = db.query(SaleTransfer).filter(SaleTransfer.id == transfer_id).first()
        if not transfer:
            return False
        db.delete(transfer)
        db.commit()
        return True
    finally:
        db.close()
