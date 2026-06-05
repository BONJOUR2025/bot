import json
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.base_class import Base


class PaymentCategory(Base):
    __tablename__ = "payment_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    sort_order = Column(Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "sort_order": self.sort_order,
        }


class PaymentSchedule(Base):
    __tablename__ = "payment_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    planned_amount = Column(Float, nullable=False)
    day_of_month = Column(Integer, nullable=False)  # 1–31
    category = Column(String, nullable=True, default="")
    responsible_name = Column(String, nullable=True, default="")
    responsible_tg_id = Column(String, nullable=True, default="")
    notify_days_before = Column(Integer, nullable=False, default=3)
    is_active = Column(Boolean, nullable=False, default=True)
    note = Column(Text, nullable=True, default="")
    objects = Column(Text, nullable=True, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)

    records = relationship("PaymentRecord", back_populates="schedule", cascade="all, delete-orphan")

    def to_dict(self):
        try:
            objects = json.loads(self.objects or "[]")
        except Exception:
            objects = []
        return {
            "id": self.id,
            "name": self.name,
            "planned_amount": self.planned_amount,
            "day_of_month": self.day_of_month,
            "category": self.category or "",
            "responsible_name": self.responsible_name or "",
            "responsible_tg_id": self.responsible_tg_id or "",
            "notify_days_before": self.notify_days_before,
            "is_active": self.is_active,
            "note": self.note or "",
            "objects": objects,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PaymentRecord(Base):
    __tablename__ = "payment_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    schedule_id = Column(Integer, ForeignKey("payment_schedules.id", ondelete="CASCADE"), nullable=False, index=True)
    year_month = Column(String(7), nullable=False, index=True)  # "YYYY-MM"
    status = Column(String, nullable=False, default="pending")  # pending / paid / skipped
    actual_amount = Column(Float, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    comment = Column(Text, nullable=True)

    schedule = relationship("PaymentSchedule", back_populates="records")

    def to_dict(self):
        return {
            "id": self.id,
            "schedule_id": self.schedule_id,
            "year_month": self.year_month,
            "status": self.status,
            "actual_amount": self.actual_amount,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "comment": self.comment or "",
        }
