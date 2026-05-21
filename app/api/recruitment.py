from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.recruitment import Candidate, Vacancy

router = APIRouter(prefix="/recruitment", tags=["Recruitment"])

VALID_STAGES = ["отклик", "собеседование", "ждем", "отказ", "нанят"]
VALID_SOURCES = ["hh", "avito", "manual", "other"]


# ── Schemas ────────────────────────────────────────────────────────

class VacancyCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    is_open: bool = True


class VacancyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_open: Optional[bool] = None


class CandidateCreate(BaseModel):
    vacancy_id: int
    name: str
    phone: Optional[str] = ""
    email: Optional[str] = ""
    source: Optional[str] = "manual"
    stage: Optional[str] = "отклик"
    notes: Optional[str] = ""


class CandidateUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    source: Optional[str] = None
    stage: Optional[str] = None
    notes: Optional[str] = None
    vacancy_id: Optional[int] = None


# ── Vacancies ──────────────────────────────────────────────────────

@router.get("/vacancies")
def list_vacancies(
    include_closed: bool = Query(False),
    db: Session = Depends(get_db),
):
    q = db.query(Vacancy)
    if not include_closed:
        q = q.filter(Vacancy.is_open == True)
    vacancies = q.order_by(Vacancy.created_at.desc()).all()
    result = []
    for v in vacancies:
        d = v.to_dict()
        d["candidate_count"] = len(v.candidates)
        result.append(d)
    return result


@router.post("/vacancies")
def create_vacancy(data: VacancyCreate, db: Session = Depends(get_db)):
    v = Vacancy(title=data.title, description=data.description, is_open=data.is_open)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v.to_dict()


@router.patch("/vacancies/{vacancy_id}")
def update_vacancy(vacancy_id: int, data: VacancyUpdate, db: Session = Depends(get_db)):
    v = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    if data.title is not None:
        v.title = data.title
    if data.description is not None:
        v.description = data.description
    if data.is_open is not None:
        v.is_open = data.is_open
    db.commit()
    db.refresh(v)
    return v.to_dict()


@router.delete("/vacancies/{vacancy_id}")
def delete_vacancy(vacancy_id: int, db: Session = Depends(get_db)):
    v = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    db.delete(v)
    db.commit()
    return {"status": "deleted"}


# ── Candidates ─────────────────────────────────────────────────────

@router.get("/candidates")
def list_candidates(
    vacancy_id: Optional[int] = Query(None),
    stage: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Candidate)
    if vacancy_id is not None:
        q = q.filter(Candidate.vacancy_id == vacancy_id)
    if stage:
        q = q.filter(Candidate.stage == stage)
    return [c.to_dict() for c in q.order_by(Candidate.created_at.asc()).all()]


@router.post("/candidates")
def create_candidate(data: CandidateCreate, db: Session = Depends(get_db)):
    if data.stage not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage. Valid: {VALID_STAGES}")
    vacancy = db.query(Vacancy).filter(Vacancy.id == data.vacancy_id).first()
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    c = Candidate(
        vacancy_id=data.vacancy_id,
        name=data.name,
        phone=data.phone or "",
        email=data.email or "",
        source=data.source or "manual",
        stage=data.stage or "отклик",
        notes=data.notes or "",
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c.to_dict()


@router.patch("/candidates/{candidate_id}")
def update_candidate(candidate_id: int, data: CandidateUpdate, db: Session = Depends(get_db)):
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if data.stage is not None and data.stage not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage. Valid: {VALID_STAGES}")
    for field in ("name", "phone", "email", "source", "stage", "notes", "vacancy_id"):
        val = getattr(data, field)
        if val is not None:
            setattr(c, field, val)
    c.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(c)
    return c.to_dict()


@router.delete("/candidates/{candidate_id}")
def delete_candidate(candidate_id: int, db: Session = Depends(get_db)):
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    db.delete(c)
    db.commit()
    return {"status": "deleted"}
