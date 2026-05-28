from sqlalchemy import Column, DateTime, Integer, String, Text
from datetime import datetime
from app.db.base_class import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    category = Column(String, nullable=False, default="Общее")
    content = Column(Text, nullable=False, default="")
    order_idx = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self, include_content=True):
        d = {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "order_idx": self.order_idx,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_content:
            d["content"] = self.content or ""
        return d
