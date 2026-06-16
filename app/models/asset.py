from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.db.base_class import Base


class Asset(Base):
    __tablename__ = "assets"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    employee_id   = Column(String, nullable=False, index=True)
    employee_name = Column(String, default="")
    position      = Column(String, default="")
    item_name     = Column(String, nullable=False)
    size          = Column(String, default="")
    quantity      = Column(Integer, default=1)
    issue_date    = Column(String, nullable=False, default="")
    return_date   = Column(String, nullable=True)
    service_life  = Column(Integer, nullable=True)
    notified_at   = Column(String, nullable=True)
    acked_at      = Column(String, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
