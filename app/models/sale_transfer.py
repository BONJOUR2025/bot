import json
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from app.db.base_class import Base


class SaleTransfer(Base):
    """A manual correction that moves a single order's sale from one employee
    to another, layered on top of the read-only Firebird data.

    Firebird is never modified — transfers are applied in-memory during payroll
    calculation (and therefore in the bot too), subtracting the amount from the
    original seller and adding it to the new one for the given month.
    """

    __tablename__ = "sale_transfers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    month_key = Column(String, nullable=False, index=True)   # "ИЮНЬ_2026"
    doc_num = Column(String, nullable=False, index=True)
    category = Column(String, nullable=False)                # repair / cosmetics / shoes
    amount = Column(Float, nullable=False, default=0.0)
    from_code = Column(String, nullable=False)
    to_code = Column(String, nullable=False)
    from_name = Column(String, default="")
    to_name = Column(String, default="")
    order_date = Column(String, default="")                  # ISO date of the order
    # For shoes: JSON list of moved pairs [{"doc_num": str, "kredit": float}, ...]
    shoes_orders = Column(Text, default="")
    author = Column(String, default="")                      # who performed the move
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        try:
            pairs = json.loads(self.shoes_orders) if self.shoes_orders else []
        except Exception:
            pairs = []
        return {
            "id": self.id,
            "month_key": self.month_key,
            "doc_num": self.doc_num,
            "category": self.category,
            "amount": self.amount,
            "from_code": self.from_code,
            "to_code": self.to_code,
            "from_name": self.from_name or "",
            "to_name": self.to_name or "",
            "order_date": self.order_date or "",
            "shoes_orders": pairs,
            "author": self.author or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
