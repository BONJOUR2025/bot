from datetime import datetime, timedelta
import logging
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import RedirectResponse

log = logging.getLogger(__name__)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.recruitment import (
    Candidate, RecruitmentSource, Vacancy, VacancyLink, TelegramMessage,
    HiringStrategy, KnowledgeBaseEntry, VacancyTemplate,
)
from app.settings import settings

from .dependencies import require_permission


def _hh_creds() -> tuple[str, str]:
    return settings.hh_client_id, settings.hh_client_secret



# Stored in-process during the brief OAuth redirect roundtrip (seconds)
_pending_hh_redirect_uri: str = ""

router = APIRouter(
    prefix="/recruitment",
    tags=["Recruitment"],
    dependencies=[Depends(require_permission("employees"))],
)

VALID_STAGES = ["отклик", "собеседование", "ждем", "ждем_привязки", "общение", "отказ", "нанят"]
VALID_SOURCES = ["hh", "avito", "manual", "other"]


# ── Pydantic schemas ───────────────────────────────────────────────

class DealBreaker(BaseModel):
    label: str
    value: str


class VacancyCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    knowledge_base: Optional[str] = ""
    interview_location: Optional[str] = ""
    is_open: bool = True
    strategy_id: Optional[int] = None
    deal_breakers: Optional[List[DealBreaker]] = None
    custom_questions: Optional[List[str]] = None
    knowledge_document_ids: Optional[List[int]] = None
    quick_mode_enabled: bool = False
    quick_questions: Optional[List[str]] = None

class VacancyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    knowledge_base: Optional[str] = None
    interview_location: Optional[str] = None
    is_open: Optional[bool] = None
    strategy_id: Optional[int] = None
    # extra_instructions is AI-facing text — can only be set together with
    # confirmed=True, after the admin has seen the AI pre-check result for it.
    extra_instructions: Optional[str] = None
    confirmed: bool = False
    deal_breakers: Optional[List[DealBreaker]] = None
    custom_questions: Optional[List[str]] = None
    knowledge_document_ids: Optional[List[int]] = None
    quick_mode_enabled: Optional[bool] = None
    quick_questions: Optional[List[str]] = None


class VacancyTemplateCreate(BaseModel):
    name: str


class StageTransition(BaseModel):
    condition: Optional[str] = ""
    next: str


class Stage(BaseModel):
    id: str
    title: str
    instructions: Optional[str] = ""
    transitions: List[StageTransition] = []
    # If true, the vacancy's custom_questions (set in the vacancy editor, not
    # the strategy) get appended to this stage's instructions when rendered
    # for a specific candidate — pins "ask these" to a concrete point in the
    # script instead of leaving the AI to pick a moment on its own.
    ask_custom_questions: bool = False


class StrategyCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    sources_str: Optional[str] = ""
    follow_up_enabled: bool = False
    follow_up_delay_hours: int = 24
    follow_up_message_1: Optional[str] = ""
    follow_up_message_2: Optional[str] = ""
    decline_after_hours: Optional[int] = None
    hh_message_with_link: Optional[str] = ""
    hh_message_no_link: Optional[str] = ""
    away_message: Optional[str] = ""
    ai_model: Optional[str] = None
    stages: Optional[List[Stage]] = None

class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    sources_str: Optional[str] = None
    follow_up_enabled: Optional[bool] = None
    follow_up_delay_hours: Optional[int] = None
    follow_up_message_1: Optional[str] = None
    follow_up_message_2: Optional[str] = None
    decline_after_hours: Optional[int] = None
    hh_message_with_link: Optional[str] = None
    hh_message_no_link: Optional[str] = None
    away_message: Optional[str] = None
    ai_model: Optional[str] = None
    stages: Optional[List[Stage]] = None


class KBEntryCreate(BaseModel):
    scope: str  # "global" | "vacancy"
    vacancy_id: Optional[int] = None
    category: Optional[str] = ""
    question: str
    answer: str
    confirmed: bool = False  # must be True — set only after AI pre-check was shown

class KBEntryUpdate(BaseModel):
    category: Optional[str] = None
    question: Optional[str] = None
    answer: Optional[str] = None
    confirmed: bool = False


class AITextCheckRequest(BaseModel):
    text: str
    scope: str  # "global" | "vacancy"
    vacancy_id: Optional[int] = None
    field_label: Optional[str] = "запись базы знаний"

class AISuggestQuestionsRequest(BaseModel):
    title: str
    description: Optional[str] = ""

class DeclineSuggestionResolve(BaseModel):
    action: str  # "decline" | "dismiss"

class CandidateCreate(BaseModel):
    vacancy_id: int
    name: str
    phone: Optional[str] = ""
    email: Optional[str] = ""
    source: Optional[str] = "manual"
    stage: Optional[str] = "отклик"
    notes: Optional[str] = ""
    age: Optional[int] = None
    resume_url: Optional[str] = ""
    photo_url: Optional[str] = ""

class CandidateUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    source: Optional[str] = None
    stage: Optional[str] = None
    notes: Optional[str] = None
    vacancy_id: Optional[int] = None
    age: Optional[int] = None
    resume_url: Optional[str] = None
    photo_url: Optional[str] = None
    rejection_message: Optional[str] = None
    hh_message: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_username: Optional[str] = None
    send_telegram: bool = False

class HHIntervalRequest(BaseModel):
    sync_interval_minutes: int = 15

class AvitoConnectRequest(BaseModel):
    client_id: str
    client_secret: str
    sync_interval_minutes: Optional[int] = 15

class LinkCreate(BaseModel):
    vacancy_id: int
    source: str
    external_vacancy_id: str
    external_vacancy_title: Optional[str] = ""

class LinkUpdate(BaseModel):
    sync_enabled: Optional[bool] = None
    external_vacancy_id: Optional[str] = None
    external_vacancy_title: Optional[str] = None

class SendMessageRequest(BaseModel):
    text: str


def _serialize_deal_breakers(deal_breakers: Optional[List[DealBreaker]]) -> Optional[str]:
    """Converts a DealBreaker list into the deal_breakers_json column value,
    dropping rows where label or value was left blank."""
    import json

    if deal_breakers is None:
        return None
    cleaned = [
        {"label": d.label.strip(), "value": d.value.strip()}
        for d in deal_breakers if d.label.strip() and d.value.strip()
    ]
    return json.dumps(cleaned, ensure_ascii=False)


def _serialize_custom_questions(questions: Optional[List[str]]) -> Optional[str]:
    """Converts a list of question strings into a JSON column value, dropping
    blanks. Used for both custom_questions_json (full Telegram interview) and
    quick_questions_json (on-platform quick screen)."""
    import json

    if questions is None:
        return None
    cleaned = [q.strip() for q in questions if q.strip()]
    return json.dumps(cleaned, ensure_ascii=False)


def _serialize_knowledge_document_ids(ids: Optional[List[int]]) -> Optional[str]:
    """Converts a list of KnowledgeDocument ids into the
    knowledge_document_ids_json column value."""
    import json

    if ids is None:
        return None
    return json.dumps(list(dict.fromkeys(ids)), ensure_ascii=False)


# ── Vacancies ──────────────────────────────────────────────────────

@router.get("/vacancies")
def list_vacancies(include_closed: bool = Query(False), db: Session = Depends(get_db)):
    q = db.query(Vacancy)
    if not include_closed:
        q = q.filter(Vacancy.is_open == True)
    result = []
    for v in q.order_by(Vacancy.created_at.desc()).all():
        d = v.to_dict()
        d["candidate_count"] = len(v.candidates)
        result.append(d)
    return result

@router.post("/vacancies")
def create_vacancy(data: VacancyCreate, db: Session = Depends(get_db)):
    if data.strategy_id is not None and not db.query(HiringStrategy).filter(HiringStrategy.id == data.strategy_id).first():
        raise HTTPException(404, "Strategy not found")
    v = Vacancy(title=data.title, description=data.description,
                knowledge_base=data.knowledge_base, interview_location=data.interview_location,
                is_open=data.is_open, strategy_id=data.strategy_id,
                deal_breakers_json=_serialize_deal_breakers(data.deal_breakers),
                custom_questions_json=_serialize_custom_questions(data.custom_questions),
                knowledge_document_ids_json=_serialize_knowledge_document_ids(data.knowledge_document_ids),
                quick_mode_enabled=data.quick_mode_enabled,
                quick_questions_json=_serialize_custom_questions(data.quick_questions))
    db.add(v); db.commit(); db.refresh(v)
    return v.to_dict()

@router.patch("/vacancies/{vacancy_id}")
def update_vacancy(vacancy_id: int, data: VacancyUpdate, db: Session = Depends(get_db)):
    v = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not v:
        raise HTTPException(404, "Vacancy not found")
    if data.extra_instructions is not None and not data.confirmed:
        raise HTTPException(
            400,
            "Особые инструкции для ИИ нельзя сохранить без предварительной ИИ-проверки. "
            "Запустите проверку текста (POST /recruitment/ai/check-text) и повторите запрос с confirmed=true.",
        )
    if data.title is not None: v.title = data.title
    if data.description is not None: v.description = data.description
    if data.knowledge_base is not None: v.knowledge_base = data.knowledge_base
    if data.interview_location is not None: v.interview_location = data.interview_location
    if data.is_open is not None: v.is_open = data.is_open
    if data.extra_instructions is not None: v.extra_instructions = data.extra_instructions
    if data.strategy_id is not None:
        if data.strategy_id and not db.query(HiringStrategy).filter(HiringStrategy.id == data.strategy_id).first():
            raise HTTPException(404, "Strategy not found")
        v.strategy_id = data.strategy_id
    if data.deal_breakers is not None:
        v.deal_breakers_json = _serialize_deal_breakers(data.deal_breakers)
    if data.custom_questions is not None:
        v.custom_questions_json = _serialize_custom_questions(data.custom_questions)
    if data.quick_mode_enabled is not None:
        v.quick_mode_enabled = data.quick_mode_enabled
    if data.quick_questions is not None:
        v.quick_questions_json = _serialize_custom_questions(data.quick_questions)
    if data.knowledge_document_ids is not None:
        v.knowledge_document_ids_json = _serialize_knowledge_document_ids(data.knowledge_document_ids)
    db.commit(); db.refresh(v)
    return v.to_dict()

@router.delete("/vacancies/{vacancy_id}")
def delete_vacancy(vacancy_id: int, db: Session = Depends(get_db)):
    v = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not v: raise HTTPException(404, "Vacancy not found")
    # The model declares ondelete="CASCADE" on KnowledgeBaseEntry.vacancy_id,
    # but SQLite only enforces FK actions when PRAGMA foreign_keys=ON for the
    # connection, which this app never sets — so that CASCADE is inert and a
    # deleted vacancy silently leaves its scoped KB entries orphaned (found
    # via a real 12-row orphan set from earlier deleted vacancies). Delete
    # them explicitly instead of relying on a constraint that isn't active.
    db.query(KnowledgeBaseEntry).filter(
        KnowledgeBaseEntry.scope == "vacancy", KnowledgeBaseEntry.vacancy_id == vacancy_id
    ).delete()
    db.delete(v); db.commit()
    return {"status": "deleted"}

@router.post("/vacancies/{vacancy_id}/duplicate")
def duplicate_vacancy(vacancy_id: int, db: Session = Depends(get_db)):
    """Create a fresh open vacancy by copying title/description/strategy/
    interview_location/extra_instructions and all vacancy-scoped knowledge
    base entries from an existing (typically closed) vacancy — so
    republishing a recurring vacancy doesn't require re-entering everything.
    """
    src = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not src: raise HTTPException(404, "Vacancy not found")

    new_title = src.title if src.is_open else f"{src.title} (копия)"
    v = Vacancy(
        title=new_title,
        description=src.description,
        knowledge_base=src.knowledge_base,
        interview_location=src.interview_location,
        is_open=True,
        strategy_id=src.strategy_id,
        extra_instructions=src.extra_instructions,
        deal_breakers_json=src.deal_breakers_json,
        custom_questions_json=src.custom_questions_json,
        knowledge_document_ids_json=src.knowledge_document_ids_json,
        quick_mode_enabled=src.quick_mode_enabled,
        quick_questions_json=src.quick_questions_json,
    )
    db.add(v); db.commit(); db.refresh(v)

    entries = db.query(KnowledgeBaseEntry).filter(
        KnowledgeBaseEntry.scope == "vacancy", KnowledgeBaseEntry.vacancy_id == vacancy_id
    ).all()
    for e in entries:
        db.add(KnowledgeBaseEntry(
            scope="vacancy", vacancy_id=v.id, category=e.category, question=e.question,
            answer=e.answer, ai_checked=e.ai_checked, ai_check_summary=e.ai_check_summary,
        ))
    db.commit()

    d = v.to_dict()
    d["candidate_count"] = 0
    return d


# ── Vacancy templates (persistent, independent of live vacancies) ──

@router.get("/vacancy-templates")
def list_vacancy_templates(db: Session = Depends(get_db)):
    return [t.to_dict() for t in db.query(VacancyTemplate).order_by(VacancyTemplate.created_at.desc()).all()]


@router.post("/vacancies/{vacancy_id}/save-as-template")
def save_vacancy_as_template(vacancy_id: int, data: VacancyTemplateCreate, db: Session = Depends(get_db)):
    """Snapshot a vacancy (incl. its vacancy-scoped knowledge base) into a
    standalone template that survives the vacancy being closed or deleted."""
    import json

    v = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not v:
        raise HTTPException(404, "Vacancy not found")

    entries = db.query(KnowledgeBaseEntry).filter(
        KnowledgeBaseEntry.scope == "vacancy", KnowledgeBaseEntry.vacancy_id == vacancy_id
    ).all()
    # Dedup by question (case-insensitive) so any duplicate rows that already
    # accumulated on the source vacancy don't get baked into the template and
    # replayed on every future vacancy created from it.
    seen_questions = set()
    kb_snapshot = []
    for e in entries:
        key = (e.question or "").strip().lower()
        if key in seen_questions:
            continue
        seen_questions.add(key)
        kb_snapshot.append({"category": e.category or "", "question": e.question, "answer": e.answer})

    t = VacancyTemplate(
        name=data.name,
        title=v.title,
        description=v.description,
        interview_location=v.interview_location,
        strategy_id=v.strategy_id,
        extra_instructions=v.extra_instructions,
        kb_entries_json=json.dumps(kb_snapshot, ensure_ascii=False),
        deal_breakers_json=v.deal_breakers_json,
        custom_questions_json=v.custom_questions_json,
        knowledge_document_ids_json=v.knowledge_document_ids_json,
    )
    db.add(t); db.commit(); db.refresh(t)
    return t.to_dict()


@router.post("/vacancy-templates/{template_id}/create-vacancy")
def create_vacancy_from_template(template_id: int, db: Session = Depends(get_db)):
    """Spin up a fresh open vacancy from a saved template, replaying its
    knowledge-base snapshot into new vacancy-scoped KnowledgeBaseEntry rows."""
    import json

    t = db.query(VacancyTemplate).filter(VacancyTemplate.id == template_id).first()
    if not t:
        raise HTTPException(404, "Template not found")

    v = Vacancy(
        title=t.title,
        description=t.description,
        interview_location=t.interview_location,
        is_open=True,
        strategy_id=t.strategy_id,
        extra_instructions=t.extra_instructions,
        deal_breakers_json=t.deal_breakers_json,
        custom_questions_json=t.custom_questions_json,
        knowledge_document_ids_json=t.knowledge_document_ids_json,
    )
    db.add(v); db.commit(); db.refresh(v)

    try:
        kb_snapshot = json.loads(t.kb_entries_json or "[]")
    except Exception:
        kb_snapshot = []
    for entry in kb_snapshot:
        db.add(KnowledgeBaseEntry(
            scope="vacancy", vacancy_id=v.id, category=entry.get("category") or "",
            question=entry.get("question") or "", answer=entry.get("answer") or "",
        ))
    db.commit()

    d = v.to_dict()
    d["candidate_count"] = 0
    return d


@router.delete("/vacancy-templates/{template_id}")
def delete_vacancy_template(template_id: int, db: Session = Depends(get_db)):
    t = db.query(VacancyTemplate).filter(VacancyTemplate.id == template_id).first()
    if not t:
        raise HTTPException(404, "Template not found")
    db.delete(t); db.commit()
    return {"status": "deleted"}


# ── Hiring strategies ──────────────────────────────────────────────

@router.get("/strategies")
def list_strategies(db: Session = Depends(get_db)):
    return [s.to_dict() for s in db.query(HiringStrategy).order_by(HiringStrategy.is_builtin.desc(), HiringStrategy.name).all()]


@router.get("/default-stages")
def get_default_stages():
    from app.services.interview_stages import DEFAULT_STAGES
    return DEFAULT_STAGES


def _pop_stages_json(payload: dict) -> dict:
    """Pulls the "stages" key (list of Stage dicts) out of a request payload
    and converts it to the stages_json column value, validating it first."""
    import json
    from app.services.interview_stages import validate_stages

    if "stages" not in payload:
        return payload
    stages = payload.pop("stages")
    if stages is None:
        payload["stages_json"] = None
        return payload
    try:
        validate_stages(stages)
    except ValueError as e:
        raise HTTPException(400, str(e))
    payload["stages_json"] = json.dumps(stages, ensure_ascii=False)
    return payload


@router.post("/strategies")
def create_strategy(data: StrategyCreate, db: Session = Depends(get_db)):
    s = HiringStrategy(**_pop_stages_json(data.dict()))
    db.add(s); db.commit(); db.refresh(s)
    return s.to_dict()


@router.patch("/strategies/{strategy_id}")
def update_strategy(strategy_id: int, data: StrategyUpdate, db: Session = Depends(get_db)):
    s = db.query(HiringStrategy).filter(HiringStrategy.id == strategy_id).first()
    if not s:
        raise HTTPException(404, "Strategy not found")
    for field, val in _pop_stages_json(data.dict(exclude_unset=True)).items():
        setattr(s, field, val)
    s.updated_at = datetime.utcnow()
    db.commit(); db.refresh(s)
    return s.to_dict()


@router.delete("/strategies/{strategy_id}")
def delete_strategy(strategy_id: int, db: Session = Depends(get_db)):
    s = db.query(HiringStrategy).filter(HiringStrategy.id == strategy_id).first()
    if not s:
        raise HTTPException(404, "Strategy not found")
    if s.is_builtin:
        raise HTTPException(400, "Встроенные стратегии нельзя удалить")
    in_use = db.query(Vacancy).filter(Vacancy.strategy_id == strategy_id).count()
    if in_use:
        raise HTTPException(400, f"Стратегия используется в {in_use} вакансии(ях) — сначала смените стратегию у них")
    in_templates = db.query(VacancyTemplate).filter(VacancyTemplate.strategy_id == strategy_id).count()
    if in_templates:
        raise HTTPException(400, f"Стратегия используется в {in_templates} шаблоне(ах) вакансий — сначала смените стратегию у них")
    db.delete(s); db.commit()
    return {"status": "deleted"}


# ── Knowledge base entries (scoped) ────────────────────────────────

@router.get("/knowledge-base")
def list_kb_entries(scope: Optional[str] = Query(None), vacancy_id: Optional[int] = Query(None),
                     db: Session = Depends(get_db)):
    q = db.query(KnowledgeBaseEntry)
    if scope: q = q.filter(KnowledgeBaseEntry.scope == scope)
    if vacancy_id is not None: q = q.filter(KnowledgeBaseEntry.vacancy_id == vacancy_id)
    return [e.to_dict() for e in q.order_by(KnowledgeBaseEntry.created_at.desc()).all()]


@router.post("/knowledge-base")
def create_kb_entry(data: KBEntryCreate, db: Session = Depends(get_db)):
    if data.scope not in ("global", "vacancy"):
        raise HTTPException(400, "scope must be 'global' or 'vacancy'")
    if data.scope == "vacancy" and not data.vacancy_id:
        raise HTTPException(400, "vacancy_id обязателен для scope='vacancy'")
    if not data.confirmed:
        raise HTTPException(
            400,
            "Нельзя сохранить запись базы знаний без предварительной ИИ-проверки. "
            "Сначала вызовите POST /recruitment/ai/check-text, покажите результат админу, "
            "затем повторите запрос с confirmed=true.",
        )
    vacancy_id = data.vacancy_id if data.scope == "vacancy" else None
    question = data.question.strip()

    # Same question already saved for this scope (e.g. an AI-suggested
    # question replayed from a vacancy template, then answered again in the
    # editor) — update it in place instead of inserting a duplicate row.
    # Compared in Python, not SQL LOWER(), since SQLite's LOWER() is
    # ASCII-only and would miss case differences in Cyrillic questions.
    same_scope = db.query(KnowledgeBaseEntry).filter(
        KnowledgeBaseEntry.scope == data.scope,
        KnowledgeBaseEntry.vacancy_id == vacancy_id,
    ).all()
    existing = next((e for e in same_scope if (e.question or "").strip().lower() == question.lower()), None)
    if existing:
        existing.category = data.category or existing.category
        existing.answer = data.answer
        existing.ai_checked = True
        db.commit(); db.refresh(existing)
        return existing.to_dict()

    e = KnowledgeBaseEntry(
        scope=data.scope, vacancy_id=vacancy_id,
        category=data.category or "", question=question, answer=data.answer,
        ai_checked=True,
    )
    db.add(e); db.commit(); db.refresh(e)
    return e.to_dict()


@router.patch("/knowledge-base/{entry_id}")
def update_kb_entry(entry_id: int, data: KBEntryUpdate, db: Session = Depends(get_db)):
    e = db.query(KnowledgeBaseEntry).filter(KnowledgeBaseEntry.id == entry_id).first()
    if not e:
        raise HTTPException(404, "Entry not found")
    if data.answer is not None and not data.confirmed:
        raise HTTPException(
            400,
            "Изменения ответа нужно подтвердить ИИ-проверкой перед сохранением (confirmed=true).",
        )
    if data.category is not None: e.category = data.category
    if data.question is not None: e.question = data.question
    if data.answer is not None:
        e.answer = data.answer
        e.ai_checked = True
    e.updated_at = datetime.utcnow()
    db.commit(); db.refresh(e)
    return e.to_dict()


@router.delete("/knowledge-base/{entry_id}")
def delete_kb_entry(entry_id: int, db: Session = Depends(get_db)):
    e = db.query(KnowledgeBaseEntry).filter(KnowledgeBaseEntry.id == entry_id).first()
    if not e:
        raise HTTPException(404, "Entry not found")
    db.delete(e); db.commit()
    return {"status": "deleted"}


# ── AI pre-check gate ───────────────────────────────────────────────

@router.post("/ai/check-text")
def ai_check_text(data: AITextCheckRequest, db: Session = Depends(get_db)):
    """Mandatory pre-save check for any AI-facing text. The frontend must
    call this and show the result to the admin before any save that touches
    KB entries / extra_instructions can be confirmed."""
    from app.services.config_service import ConfigService
    from app.services.ai_text_check import check_text

    if data.scope not in ("global", "vacancy"):
        raise HTTPException(400, "scope must be 'global' or 'vacancy'")
    vacancy_title = None
    if data.vacancy_id:
        v = db.query(Vacancy).filter(Vacancy.id == data.vacancy_id).first()
        vacancy_title = v.title if v else None

    cfg = ConfigService().load()
    return check_text(cfg, data.text, data.scope, vacancy_title=vacancy_title,
                       field_label=data.field_label or "запись базы знаний")


@router.post("/ai/suggest-questions")
def ai_suggest_questions(data: AISuggestQuestionsRequest):
    """Used by the vacancy-creation wizard to proactively propose a list of
    likely candidate questions for the admin to answer (instead of leaving
    the admin to invent the FAQ from scratch)."""
    from app.services.config_service import ConfigService
    from app.services.ai_text_check import generate_candidate_questions

    cfg = ConfigService().load()
    try:
        questions = generate_candidate_questions(cfg, data.title, data.description or "")
    except RuntimeError as e:
        raise HTTPException(502, detail=str(e))
    return {"questions": questions}


@router.get("/vacancies/{vacancy_id}/checklist")
def vacancy_checklist(vacancy_id: int, db: Session = Depends(get_db)):
    """Computed (not stored) readiness checklist — what's still missing
    before this vacancy is safe to launch with AI automation."""
    from app.services.config_service import ConfigService
    from app.services.llm_client import get_client

    v = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not v:
        raise HTTPException(404, "Vacancy not found")

    cfg = ConfigService().load()
    has_global_kb = db.query(KnowledgeBaseEntry).filter(KnowledgeBaseEntry.scope == "global").count() > 0
    has_vacancy_kb = db.query(KnowledgeBaseEntry).filter(
        KnowledgeBaseEntry.scope == "vacancy", KnowledgeBaseEntry.vacancy_id == vacancy_id
    ).count() > 0

    items = [
        {"key": "api_key", "label": "Настроен AI-провайдер (API-ключ)", "done": bool(get_client(cfg))},
        {"key": "knowledge_base", "label": "Есть хотя бы один пункт базы знаний (общий или для вакансии)",
         "done": has_global_kb or has_vacancy_kb},
        {"key": "interview_location", "label": "Указано место/формат собеседования",
         "done": bool((v.interview_location or "").strip() or (cfg.get("automation_interview_location") or "").strip())},
        {"key": "strategy", "label": "Выбрана стратегия найма", "done": bool(v.strategy_id)},
    ]
    return {"items": items, "ready": all(i["done"] for i in items)}


# ── Candidates ─────────────────────────────────────────────────────

@router.get("/candidates")
def list_candidates(
    vacancy_id: Optional[int] = Query(None),
    stage: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Candidate)
    if vacancy_id is not None: q = q.filter(Candidate.vacancy_id == vacancy_id)
    if stage: q = q.filter(Candidate.stage == stage)
    candidates = q.order_by(Candidate.created_at.asc()).all()

    # Compute per-candidate flags
    since_24h = datetime.utcnow() - timedelta(hours=24)
    # Collect candidate IDs with unread TG messages
    try:
        unread_tg_ids = {
            row[0] for row in db.query(TelegramMessage.candidate_id).filter(
                TelegramMessage.direction == "in",
                TelegramMessage.is_read == False,
            ).all()
        }
    except Exception:
        unread_tg_ids = set()

    result = []
    for c in candidates:
        d = c.to_dict()
        d["is_new"] = bool(c.created_at and c.created_at >= since_24h)
        d["has_unread_hh_msg"] = bool(getattr(c, "has_unread_hh_msg", False))
        d["has_unread_tg"] = c.id in unread_tg_ids
        d["vacancy_title"] = c.vacancy.title if c.vacancy else ""
        result.append(d)
    return result

@router.post("/candidates")
def create_candidate(data: CandidateCreate, db: Session = Depends(get_db)):
    if data.stage not in VALID_STAGES:
        raise HTTPException(400, f"Invalid stage. Valid: {VALID_STAGES}")
    if not db.query(Vacancy).filter(Vacancy.id == data.vacancy_id).first():
        raise HTTPException(404, "Vacancy not found")
    c = Candidate(
        vacancy_id=data.vacancy_id, name=data.name,
        phone=data.phone or "", email=data.email or "",
        source=data.source or "manual", stage=data.stage or "отклик",
        notes=data.notes or "", age=data.age,
        resume_url=data.resume_url or "",
        photo_url=data.photo_url or "",
    )
    db.add(c); db.commit(); db.refresh(c)
    return c.to_dict()

@router.patch("/candidates/{candidate_id}")
async def update_candidate(candidate_id: int, data: CandidateUpdate, db: Session = Depends(get_db)):
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c: raise HTTPException(404, "Candidate not found")
    if data.stage is not None and data.stage not in VALID_STAGES:
        raise HTTPException(400, f"Invalid stage. Valid: {VALID_STAGES}")

    old_stage = c.stage

    for field in ("name", "phone", "email", "source", "stage", "notes", "vacancy_id",
                  "age", "resume_url", "photo_url", "telegram_chat_id", "telegram_username"):
        val = getattr(data, field)
        if val is not None: setattr(c, field, val)
    c.updated_at = datetime.utcnow()
    db.commit(); db.refresh(c)

    warnings: list[str] = []

    # Push stage change to hh.ru when applicable
    if (
        data.stage and data.stage != old_stage
        and c.source == "hh"
        and c.external_id
    ):
        src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "hh").first()
        if src and src.access_token:
            try:
                from app.services import hh_api
                await hh_api.sync_negotiation_stage(
                    src.access_token, c.external_id, data.stage,
                    rejection_message=data.rejection_message or None,
                    hh_message=data.hh_message or None,
                )
            except Exception as exc:
                log.warning("hh stage sync failed for candidate %s: %s", candidate_id, exc)

    # Send via Telegram Secretary Mode if requested
    tg_chat_id = c.telegram_chat_id or ""
    tg_text = data.hh_message or data.rejection_message or ""
    if data.send_telegram and tg_chat_id and tg_text:
        from app.services.notify import send_secretary_message
        err = await send_secretary_message(tg_chat_id, tg_text)
        if err:
            warnings.append(err)

    result = c.to_dict()
    if warnings:
        result["warnings"] = warnings
    return result


@router.post("/candidates/{candidate_id}/resolve-telegram")
async def resolve_telegram_username(candidate_id: int, db: Session = Depends(get_db)):
    """Resolve candidate's telegram_username → chat_id via getChat API."""
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    username = (c.telegram_username or "").strip().lstrip("@")
    if not username:
        raise HTTPException(400, "telegram_username не заполнен")

    import httpx
    from app.config import TOKEN
    if not TOKEN:
        raise HTTPException(500, "Telegram bot token не настроен")

    from app.settings import settings as _settings
    proxy = getattr(_settings, "telegram_proxy", None)
    client_kwargs: dict = {"timeout": 10.0}
    if proxy:
        client_kwargs["proxy"] = proxy

    async with httpx.AsyncClient(**client_kwargs) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{TOKEN}/getChat",
            json={"chat_id": f"@{username}"},
        )

    if r.status_code != 200:
        data = r.json() if r.content else {}
        raise HTTPException(400, data.get("description") or f"Telegram: HTTP {r.status_code}")

    chat = r.json().get("result", {})
    chat_id = str(chat.get("id", ""))
    if not chat_id:
        raise HTTPException(400, "Не удалось получить chat_id")

    c.telegram_chat_id = chat_id
    db.commit()
    db.refresh(c)
    return {"chat_id": chat_id, "candidate": c.to_dict()}


@router.get("/candidates/{candidate_id}/telegram-messages")
def get_telegram_messages(candidate_id: int, db: Session = Depends(get_db)):
    msgs = db.query(TelegramMessage).filter(
        TelegramMessage.candidate_id == candidate_id
    ).order_by(TelegramMessage.created_at).all()
    # Mark incoming messages as read when admin opens TG chat
    try:
        updated = False
        for m in msgs:
            if m.direction == "in" and not getattr(m, 'is_read', True):
                m.is_read = True
                updated = True
        if updated:
            db.commit()
    except Exception:
        pass
    return [m.to_dict() for m in msgs]


@router.post("/candidates/{candidate_id}/telegram-messages")
async def send_telegram_message(candidate_id: int, data: SendMessageRequest, db: Session = Depends(get_db)):
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    if not c.telegram_chat_id:
        raise HTTPException(400, "Telegram chat_id не найден. Укажите username и нажмите Найти.")

    from app.services.notify import send_secretary_message
    err = await send_secretary_message(c.telegram_chat_id, data.text)
    if err:
        # Add config diagnostics to help debug
        try:
            from app.services.config_service import ConfigService
            cfg = ConfigService().load()
            conn_id = cfg.get("tg_business_connection_id", "")
            can_reply = cfg.get("tg_business_can_reply", "NOT SET")
            log.warning("Secretary send failed. config: connection_id=%r can_reply=%r", conn_id, can_reply)
            raise HTTPException(400, f"{err} [diag: connection_id={'set' if conn_id else 'EMPTY'}, can_reply={can_reply!r}]")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(400, err)

    msg = TelegramMessage(candidate_id=candidate_id, direction="out", text=data.text)
    db.add(msg)
    if c.pending_question:
        c.pending_question = None
        c.pending_question_asked_at = None
    db.commit()
    db.refresh(msg)
    return msg.to_dict()


@router.delete("/candidates/{candidate_id}")
def delete_candidate(candidate_id: int, db: Session = Depends(get_db)):
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c: raise HTTPException(404, "Candidate not found")
    db.delete(c); db.commit()
    return {"status": "deleted"}


@router.post("/candidates/{candidate_id}/reset-history")
def reset_candidate_history(candidate_id: int, db: Session = Depends(get_db)):
    """Delete all Telegram messages and reset automation state for a clean test."""
    from datetime import datetime
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")

    deleted = db.query(TelegramMessage).filter(
        TelegramMessage.candidate_id == candidate_id
    ).delete(synchronize_session=False)

    c.follow_up_count = 0
    c.follow_up_last_sent_at = None
    c.pending_interview_date = None
    c.pending_interview_time = None
    c.pending_interview_place = None
    c.stage = "отклик"
    c.updated_at = datetime.utcnow()
    db.commit()

    return {"status": "reset", "messages_deleted": deleted}


@router.post("/candidates/{candidate_id}/generate-profile")
async def generate_candidate_profile_now(candidate_id: int, db: Session = Depends(get_db)):
    """Manually (re)generate the candidate profile — recovery tool for
    interviews that finished (reached the closing message) but never
    formally reached phase "done", e.g. candidates stuck before the fix
    that cascades a stage with only an unconditional transition straight
    through to "done" instead of waiting for a message that never comes."""
    from app.services.ai_conversation import _generate_candidate_profile_inner

    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    if c.interview_phase != "done":
        c.interview_phase = "done"
        db.commit()

    success, _ = await _generate_candidate_profile_inner(candidate_id)
    if not success:
        raise HTTPException(500, "Не удалось сформировать профиль — посмотрите логи")
    db.refresh(c)
    return c.to_dict()


@router.post("/candidates/{candidate_id}/decline-suggestion")
def resolve_decline_suggestion(candidate_id: int, data: DeclineSuggestionResolve, db: Session = Depends(get_db)):
    """Admin's explicit decision on a system-suggested decline. The system
    never changes stage on its own — only ever sets pending_decline_suggested_at
    and notifies the admin; this endpoint is the only place stage actually
    changes as a result of a decline suggestion."""
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    if data.action not in ("decline", "dismiss"):
        raise HTTPException(400, "action must be 'decline' or 'dismiss'")

    if data.action == "decline":
        c.stage = "отказ"
    else:
        # Give the candidate more time: reset follow-up timer for one more cycle
        c.follow_up_count = 0
        c.follow_up_last_sent_at = datetime.utcnow()
    c.pending_decline_suggested_at = None
    c.updated_at = datetime.utcnow()
    db.commit(); db.refresh(c)
    return c.to_dict()


@router.post("/candidates/{candidate_id}/toggle-pause")
def toggle_pause(candidate_id: int, db: Session = Depends(get_db)):
    """Pause or unpause AI automation for this candidate."""
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    c.is_paused = not bool(c.is_paused)
    c.updated_at = datetime.utcnow()
    db.commit()
    return {"id": c.id, "is_paused": bool(c.is_paused)}


@router.get("/interviews")
async def list_interviews(db: Session = Depends(get_db)):
    """Return candidates at 'собеседование' stage with their interview task details."""
    from app.services.task_service import get_task_service

    candidates = db.query(Candidate).filter(
        Candidate.stage == "собеседование"
    ).order_by(Candidate.updated_at.desc()).all()

    try:
        tasks = await get_task_service().list_tasks(category="Подбор персонала")
    except Exception:
        tasks = []

    result = []
    for c in candidates:
        task = next((t for t in tasks if c.name in (t.title or "") and not (t.status == "done")), None)
        entry = c.to_dict()
        entry["interview_date"] = task.due_date if task else None
        entry["interview_time"] = task.due_time if task else None
        raw_desc = (task.description or "") if task else ""
        entry["interview_place"] = raw_desc.replace("📍 Место: ", "").strip() or None
        result.append(entry)
    return result


def _get_hh_candidate(candidate_id: int, db):
    """Return (candidate, hh_token) or raise HTTPException."""
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    if c.source != "hh" or not c.external_id:
        raise HTTPException(400, "Переписка доступна только для кандидатов с hh.ru")
    src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "hh").first()
    if not src or not src.access_token:
        raise HTTPException(400, "hh.ru не подключён")
    return c, src.access_token


@router.get("/candidates/{candidate_id}/messages")
async def get_candidate_messages(candidate_id: int, db: Session = Depends(get_db)):
    c, token = _get_hh_candidate(candidate_id, db)
    # Clear unread flag when admin opens hh chat
    if getattr(c, 'has_unread_hh_msg', False):
        try:
            c.has_unread_hh_msg = False
            db.commit()
        except Exception:
            pass
    from app.services import hh_api
    try:
        return await hh_api.get_messages(token, c.external_id)
    except Exception as exc:
        raise HTTPException(502, f"Ошибка hh.ru: {exc}")


@router.post("/candidates/{candidate_id}/messages")
async def send_candidate_message(candidate_id: int, data: SendMessageRequest, db: Session = Depends(get_db)):
    if not data.text.strip():
        raise HTTPException(400, "Текст сообщения не может быть пустым")
    c, token = _get_hh_candidate(candidate_id, db)
    from app.services import hh_api
    try:
        return await hh_api.send_message(token, c.external_id, data.text.strip())
    except ValueError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Ошибка hh.ru: {exc}")


# ── Integration sources ────────────────────────────────────────────

@router.get("/integrations")
def list_integrations(db: Session = Depends(get_db)):
    sources = db.query(RecruitmentSource).all()
    src_map = {s.source: s.to_dict() for s in sources}
    result = []
    for source_key, configured in [
        ("hh",    bool(settings.hh_client_id and settings.hh_client_secret)),
        ("avito", True),  # Avito credentials stored in DB, always show connect button
    ]:
        entry = src_map.get(source_key, {"source": source_key, "is_active": False,
                                         "employer_name": "", "last_error": "",
                                         "sync_interval_minutes": 15})
        entry["env_configured"] = configured
        result.append(entry)
    return result


@router.get("/integrations/hh/auth-url")
async def hh_auth_url(redirect_uri: str = Query(...)):
    """Return OAuth authorization URL. Credentials come from env."""
    global _pending_hh_redirect_uri
    from app.services import hh_api

    hh_id, hh_secret = _hh_creds()
    if not hh_id or not hh_secret:
        raise HTTPException(503, "hh.ru не настроен на сервере (HH_CLIENT_ID / HH_CLIENT_SECRET)")

    _pending_hh_redirect_uri = redirect_uri
    return {"auth_url": hh_api.build_auth_url(hh_id, redirect_uri)}


@router.get("/integrations/hh/callback", include_in_schema=False)
async def hh_callback(
    code: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Browser callback after hh.ru OAuth authorization."""
    global _pending_hh_redirect_uri
    from app.services import hh_api

    if error:
        return RedirectResponse(f"/admin/recruitment?hh_error={error}")
    if not code:
        return RedirectResponse("/admin/recruitment?hh_error=no_code")
    hh_id, hh_secret = _hh_creds()
    if not hh_id or not hh_secret:
        return RedirectResponse("/admin/recruitment?hh_error=not_configured")

    redirect_uri = _pending_hh_redirect_uri
    if not redirect_uri:
        return RedirectResponse("/admin/recruitment?hh_error=session_expired")

    try:
        token_data = await hh_api.exchange_code(hh_id, hh_secret, code, redirect_uri)
    except Exception as e:
        src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "hh").first()
        if src:
            src.last_error = str(e)[:500]
            db.commit()
        return RedirectResponse("/admin/recruitment?hh_error=token_exchange")

    try:
        info = await hh_api.verify_token(token_data["access_token"])
    except Exception:
        info = {"employer_id": "", "employer_name": ""}

    src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "hh").first()
    if not src:
        src = RecruitmentSource(source="hh")
        db.add(src)

    src.access_token = token_data["access_token"]
    src.refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in")
    if expires_in:
        src.token_expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))
    src.employer_id = info["employer_id"]
    src.employer_name = info["employer_name"]
    src.is_active = True
    src.last_error = ""
    src.updated_at = datetime.utcnow()
    db.commit()

    _pending_hh_redirect_uri = ""
    return RedirectResponse("/admin/recruitment?hh_connected=1")


@router.delete("/integrations/hh/disconnect")
def disconnect_hh(db: Session = Depends(get_db)):
    src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "hh").first()
    if src:
        src.is_active = False
        src.access_token = ""
        src.refresh_token = ""
        src.last_error = ""
        db.commit()
    return {"status": "disconnected"}


@router.get("/integrations/hh/vacancies")
async def hh_vacancies(db: Session = Depends(get_db)):
    src = db.query(RecruitmentSource).filter(
        RecruitmentSource.source == "hh",
        RecruitmentSource.is_active == True,
    ).first()
    if not src:
        raise HTTPException(400, "hh.ru не подключён")
    from app.services import hh_api
    try:
        return await hh_api.get_vacancies(src.access_token, src.employer_id)
    except Exception as e:
        raise HTTPException(502, f"Ошибка hh.ru: {e}")


@router.post("/integrations/avito/connect")
async def connect_avito(data: AvitoConnectRequest, db: Session = Depends(get_db)):
    """Connect Avito — credentials stored in DB, no env vars needed."""
    from app.services import avito_api
    try:
        tok  = await avito_api.get_token(data.client_id, data.client_secret)
        info = await avito_api.get_user_info(tok["access_token"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Авито недоступен: {e}")

    src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "avito").first()
    if not src:
        src = RecruitmentSource(source="avito")
        db.add(src)

    src.client_id    = data.client_id
    src.client_secret = data.client_secret
    src.access_token = tok["access_token"]
    src.employer_id  = info["employer_id"]
    src.employer_name = info["employer_name"]
    src.is_active    = True
    src.last_error   = ""
    src.sync_interval_minutes = max(1, data.sync_interval_minutes or 15)
    src.updated_at   = datetime.utcnow()
    db.commit(); db.refresh(src)
    return src.to_dict()


@router.delete("/integrations/avito/disconnect")
def disconnect_avito(db: Session = Depends(get_db)):
    src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "avito").first()
    if src:
        src.is_active    = False
        src.access_token = ""
        src.client_id    = ""
        src.client_secret = ""
        src.last_error   = ""
        db.commit()
    return {"status": "disconnected"}


@router.get("/integrations/avito/vacancies")
async def avito_vacancies(db: Session = Depends(get_db)):
    return []


@router.get("/integrations/avito/vacancy/{vacancy_id}")
async def avito_vacancy_by_id(vacancy_id: str, db: Session = Depends(get_db)):
    """Lookup a single Avito vacancy by ID to validate and get its title."""
    src = db.query(RecruitmentSource).filter(
        RecruitmentSource.source == "avito",
        RecruitmentSource.is_active == True,
    ).first()
    if not src:
        raise HTTPException(400, "Авито не подключён")
    from app.services import avito_api
    try:
        tok = await avito_api.get_token(src.client_id, src.client_secret)
        result = await avito_api.get_vacancy_by_id(tok["access_token"], vacancy_id)
        if result is None:
            raise HTTPException(404, "Вакансия не найдена")
        return result
    except HTTPException:
        raise
    except Exception as e:
        log.error("avito_vacancy_by_id error: %s", e, exc_info=True)
        raise HTTPException(502, f"Ошибка Авито: {e}")


@router.patch("/integrations/{source}/interval")
def update_interval(source: str, interval_minutes: int, db: Session = Depends(get_db)):
    src = db.query(RecruitmentSource).filter(RecruitmentSource.source == source).first()
    if not src: raise HTTPException(404, "Source not found")
    src.sync_interval_minutes = max(1, interval_minutes)
    db.commit()
    return src.to_dict()


# ── Vacancy links ──────────────────────────────────────────────────

@router.get("/links")
def list_links(vacancy_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    q = db.query(VacancyLink)
    if vacancy_id: q = q.filter(VacancyLink.vacancy_id == vacancy_id)
    return [link.to_dict() for link in q.all()]


@router.post("/links")
def create_link(data: LinkCreate, db: Session = Depends(get_db)):
    if data.source not in ("hh", "avito"):
        raise HTTPException(400, "source must be 'hh' or 'avito'")
    src = db.query(RecruitmentSource).filter(
        RecruitmentSource.source == data.source,
        RecruitmentSource.is_active == True,
    ).first()
    if not src:
        raise HTTPException(400, f"Источник {data.source} не подключён")
    # Check uniqueness (one source per vacancy)
    existing = db.query(VacancyLink).filter(
        VacancyLink.vacancy_id == data.vacancy_id,
        VacancyLink.source == data.source,
    ).first()
    if existing:
        # Update instead
        existing.external_vacancy_id = data.external_vacancy_id
        existing.external_vacancy_title = data.external_vacancy_title or ""
        existing.sync_enabled = True
        db.commit(); db.refresh(existing)
        return existing.to_dict()

    link = VacancyLink(
        vacancy_id=data.vacancy_id,
        source=data.source,
        source_id=src.id,
        external_vacancy_id=data.external_vacancy_id,
        external_vacancy_title=data.external_vacancy_title or "",
        sync_enabled=True,
    )
    db.add(link); db.commit(); db.refresh(link)
    return link.to_dict()


@router.patch("/links/{link_id}")
def update_link(link_id: int, data: LinkUpdate, db: Session = Depends(get_db)):
    link = db.query(VacancyLink).filter(VacancyLink.id == link_id).first()
    if not link: raise HTTPException(404, "Link not found")
    if data.sync_enabled is not None: link.sync_enabled = data.sync_enabled
    if data.external_vacancy_id is not None: link.external_vacancy_id = data.external_vacancy_id
    if data.external_vacancy_title is not None: link.external_vacancy_title = data.external_vacancy_title
    db.commit(); db.refresh(link)
    return link.to_dict()


@router.delete("/links/{link_id}")
def delete_link(link_id: int, db: Session = Depends(get_db)):
    link = db.query(VacancyLink).filter(VacancyLink.id == link_id).first()
    if not link: raise HTTPException(404, "Link not found")
    db.delete(link); db.commit()
    return {"status": "deleted"}


# ── Telegram link code ─────────────────────────────────────────────

@router.get("/candidates/{candidate_id}/telegram-link")
def get_telegram_link(candidate_id: int, db: Session = Depends(get_db)):
    """Generate or return existing link code + t.me deep link for candidate."""
    import secrets, string
    from urllib.parse import quote
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    if not getattr(c, 'telegram_link_code', None):
        alphabet = string.ascii_uppercase + string.digits
        token = ''.join(secrets.choice(alphabet) for _ in range(6))
        code = f"CAND-{candidate_id}-{token}"
        try:
            c.telegram_link_code = code
            # Помечаем кандидата как ожидающего привязку — это не только для красоты:
            # этап используется как один из триггеров запуска ИИ-собеседования при
            # получении сообщения с кодом (см. business_connection.py).
            if c.stage not in ('общение', 'отказ', 'нанят') and not c.telegram_chat_id:
                c.stage = 'ждем_привязки'
            db.commit()
        except Exception:
            pass
    else:
        code = c.telegram_link_code

    # Build t.me deep link if personal username is configured
    from app.services.config_service import ConfigService
    cfg = ConfigService().load()
    personal_username = (cfg.get("tg_personal_username") or "").strip().lstrip("@")
    tg_link = None
    prefilled_text = (
        f"{code}\n\n"
        f"(Не удаляйте и не изменяйте это сообщение — просто отправьте его, как есть, "
        f"чтобы мы могли продолжить общение)"
    )
    if personal_username:
        tg_link = f"https://t.me/{personal_username}?text={quote(prefilled_text)}"

    return {"code": code, "tg_link": tg_link, "personal_username": personal_username}


# ── Notifications summary ──────────────────────────────────────────

@router.get("/notifications")
def get_notifications(db: Session = Depends(get_db)):
    """Return unread counts for dashboard badges."""
    from sqlalchemy import text
    since = datetime.utcnow() - timedelta(hours=24)
    new_candidates = db.query(Candidate).filter(Candidate.created_at >= since).count()

    try:
        unread_hh = db.query(Candidate).filter(Candidate.has_unread_hh_msg == True).count()
    except Exception:
        try:
            unread_hh = db.execute(
                text("SELECT COUNT(*) FROM candidates WHERE has_unread_hh_msg = 1")
            ).scalar() or 0
        except Exception:
            unread_hh = 0

    try:
        unread_tg = db.query(TelegramMessage).filter(
            TelegramMessage.direction == "in",
            TelegramMessage.is_read == False,
        ).count()
    except Exception:
        try:
            unread_tg = db.execute(
                text("SELECT COUNT(*) FROM telegram_messages WHERE direction='in' AND is_read=0")
            ).scalar() or 0
        except Exception:
            unread_tg = 0

    try:
        cutoff_24h = datetime.utcnow() - timedelta(hours=24)
        pending_tg = db.query(Candidate).filter(
            Candidate.stage == "ждем_привязки",
            Candidate.updated_at <= cutoff_24h,
        ).count()
    except Exception:
        pending_tg = 0

    return {
        "new_candidates": new_candidates,
        "unread_hh": unread_hh,
        "unread_tg": unread_tg,
        "pending_tg_24h": pending_tg,
    }


# ── Automation ────────────────────────────────────────────────────

@router.get("/automation/status")
def get_automation_status():
    from app.services.automation import is_enabled
    return {"enabled": is_enabled()}

@router.post("/automation/toggle")
def toggle_automation(data: dict = Body({})):
    from app.services.automation import set_enabled, is_enabled
    val = data.get("enabled")
    if val is None:
        val = not is_enabled()
    set_enabled(bool(val))
    return {"enabled": is_enabled()}

@router.post("/candidates/{candidate_id}/test-automation")
async def test_automation(candidate_id: int):
    from app.services.automation import trigger_for_candidate
    result = await trigger_for_candidate(candidate_id, force=True)
    return {"result": result}


# ── Manual sync trigger ────────────────────────────────────────────

@router.post("/sync")
async def trigger_sync(background_tasks: BackgroundTasks):
    from app.services import recruitment_sync
    background_tasks.add_task(recruitment_sync.run_now)
    return {"status": "sync_started"}
