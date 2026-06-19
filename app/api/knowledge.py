from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.models.knowledge import KnowledgeDocument

from .dependencies import require_permission

router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(require_permission("employees"))],
)


class DocCreate(BaseModel):
    title: str
    category: str = "Общее"
    content: str = ""
    order_idx: int = 0

class DocUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    content: Optional[str] = None
    order_idx: Optional[int] = None


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(KnowledgeDocument).order_by(
        KnowledgeDocument.order_idx, KnowledgeDocument.id
    ).all()
    return [d.to_dict() for d in docs]


@router.post("/documents")
def create_document(data: DocCreate, db: Session = Depends(get_db)):
    doc = KnowledgeDocument(**data.model_dump())
    db.add(doc); db.commit(); db.refresh(doc)
    return doc.to_dict()


@router.patch("/documents/{doc_id}")
def update_document(doc_id: int, data: DocUpdate, db: Session = Depends(get_db)):
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
    if not doc: raise HTTPException(404, "Document not found")
    for field, val in data.model_dump(exclude_none=True).items():
        setattr(doc, field, val)
    db.commit(); db.refresh(doc)
    return doc.to_dict()


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
    if not doc: raise HTTPException(404, "Document not found")
    db.delete(doc); db.commit()
    return {"status": "deleted"}


@router.get("/documents/full-text")
def full_text(db: Session = Depends(get_db)):
    """Returns all documents concatenated — for Claude context."""
    docs = db.query(KnowledgeDocument).order_by(
        KnowledgeDocument.order_idx, KnowledgeDocument.id
    ).all()
    parts = []
    for d in docs:
        if d.content and d.content.strip():
            parts.append(f"=== {d.title} ({d.category}) ===\n{d.content.strip()}")
    return {"text": "\n\n".join(parts), "doc_count": len(docs)}
