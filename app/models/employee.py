from sqlalchemy import Column, Integer, String, Date, Text, DateTime, Boolean
from sqlalchemy.sql import func
from app.db.base_class import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    card_number = Column(String, nullable=False)
    bank = Column(String, nullable=False)
    birthdate = Column(Date, nullable=True)
    note = Column(Text, nullable=True)
    photo_url = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    archived = Column(Boolean, nullable=False, default=False)
    archived_at = Column(DateTime(timezone=True), nullable=True)
