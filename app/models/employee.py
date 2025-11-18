from sqlalchemy import Boolean, Column, Date, DateTime, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.sql import func

from app.db.base_class import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    full_name = Column(String, nullable=False, default="")
    phone = Column(String, nullable=False)
    position = Column(String, nullable=False, default="")
    is_admin = Column(Boolean, nullable=False, default=False)
    card_number = Column(String, nullable=False, default="")
    bank = Column(String, nullable=False, default="")
    work_place = Column(String, nullable=False, default="")
    clothing_size = Column(String, nullable=False, default="")
    birthdate = Column(Date, nullable=True)
    note = Column(Text, nullable=True)
    photo_url = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    tags = Column(JSON, nullable=False, default=list)
    payout_chat_key = Column(String, nullable=True)
    archived = Column(Boolean, nullable=False, default=False)
    archived_at = Column(DateTime(timezone=True), nullable=True)
