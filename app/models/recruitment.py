from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.base_class import Base


class HiringStrategy(Base):
    """Named automation preset (filters, follow-ups, hh templates, AI model).

    Once a vacancy has a strategy assigned, the strategy is the sole source
    of truth for these parameters — there is no global-config fallback for
    a vacancy that has a strategy. follow_up_enabled defaults to False for
    every strategy (builtin or admin-created) by design.
    """
    __tablename__ = "hiring_strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True, default="")
    is_builtin = Column(Boolean, nullable=False, default=False)

    age_min = Column(Integer, nullable=True)
    age_max = Column(Integer, nullable=True)
    sources_str = Column(String, nullable=True, default="")  # comma-separated, empty = any

    follow_up_enabled = Column(Boolean, nullable=False, default=False)
    follow_up_delay_hours = Column(Integer, nullable=False, default=24)
    follow_up_message_1 = Column(Text, nullable=True, default="")
    follow_up_message_2 = Column(Text, nullable=True, default="")

    # If set, after follow-ups are exhausted with no reply for this many hours
    # the admin gets a decline *suggestion* — never an automatic decline.
    decline_after_hours = Column(Integer, nullable=True)

    hh_message_with_link = Column(Text, nullable=True, default="")
    hh_message_no_link = Column(Text, nullable=True, default="")
    away_message = Column(Text, nullable=True, default="")
    ai_model = Column(String, nullable=True)

    # JSON list of interview stages (see app/services/interview_stages.py).
    # Null/empty = use the built-in default flow.
    stages_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        from app.services.interview_stages import get_stages
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "is_builtin": bool(self.is_builtin),
            "age_min": self.age_min,
            "age_max": self.age_max,
            "sources_str": self.sources_str or "",
            "follow_up_enabled": bool(self.follow_up_enabled),
            "follow_up_delay_hours": self.follow_up_delay_hours,
            "follow_up_message_1": self.follow_up_message_1 or "",
            "follow_up_message_2": self.follow_up_message_2 or "",
            "decline_after_hours": self.decline_after_hours,
            "hh_message_with_link": self.hh_message_with_link or "",
            "hh_message_no_link": self.hh_message_no_link or "",
            "away_message": self.away_message or "",
            "ai_model": self.ai_model,
            "stages": get_stages(self),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class KnowledgeBaseEntry(Base):
    """One scoped fact for the AI candidate-conversation knowledge base.

    scope='global' entries apply to every vacancy; scope='vacancy' entries
    apply only to vacancy_id. Structural scoping (instead of one free-text
    blob) is what prevents a vacancy-specific fact from silently leaking
    into every other vacancy's conversations.
    """
    __tablename__ = "knowledge_base_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scope = Column(String, nullable=False, default="global")  # "global" | "vacancy"
    vacancy_id = Column(Integer, ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=True, index=True)
    category = Column(String, nullable=True, default="")
    question = Column(String, nullable=False, default="")
    answer = Column(Text, nullable=False, default="")
    ai_checked = Column(Boolean, nullable=False, default=False)
    ai_check_summary = Column(Text, nullable=True, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    vacancy = relationship("Vacancy")

    def to_dict(self):
        return {
            "id": self.id,
            "scope": self.scope,
            "vacancy_id": self.vacancy_id,
            "vacancy_title": self.vacancy.title if self.vacancy else None,
            "category": self.category or "",
            "question": self.question or "",
            "answer": self.answer or "",
            "ai_checked": bool(self.ai_checked),
            "ai_check_summary": self.ai_check_summary or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Vacancy(Base):
    __tablename__ = "vacancies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True, default="")
    # Deprecated free-text KB blob — kept for backward compatibility with old
    # data only. New knowledge goes into scoped KnowledgeBaseEntry rows so the
    # UI/AI always know exactly which vacancy (or "all vacancies") a fact
    # belongs to, instead of one untyped string that's easy to mix up.
    knowledge_base = Column(Text, nullable=True, default="")
    interview_location = Column(String, nullable=True, default="")
    is_open = Column(Boolean, nullable=False, default=True)
    strategy_id = Column(Integer, ForeignKey("hiring_strategies.id", ondelete="SET NULL"), nullable=True)
    # Free-text per-vacancy overrides ("не предлагай собеседование раньше пятницы" etc.)
    # — applied on top of whatever strategy is selected, never silently merged
    # into the global/strategy knowledge base.
    extra_instructions = Column(Text, nullable=True, default="")
    # Structured "checklist" of must-match criteria (e.g. location, work
    # format, salary expectation) as a flexible [{"label", "value"}, ...]
    # list — fed into the AI context block so a strategy stage that says
    # "проверь deal-breakers" has concrete facts to check against, instead
    # of relying on free-text knowledge-base entries the AI has to infer
    # relevance from.
    deal_breakers_json = Column(Text, nullable=True)
    # Specific questions the recruiter wants asked of every candidate for this
    # vacancy — distinct from deal-breakers (not pass/fail criteria) and from
    # vacancy-scoped KnowledgeBaseEntry rows (those are FAQ answers given TO
    # the candidate, not questions asked OF them). Answers are extracted from
    # the interview transcript into the final profile sent to the recruiter.
    # [str, ...]
    custom_questions_json = Column(Text, nullable=True)
    # IDs of KnowledgeDocument rows (the free-text "База знаний" page, e.g.
    # "О компании") explicitly granted to this vacancy's candidate-facing AI
    # context. Opt-in rather than auto-including everything — those documents
    # are written for the internal staff assistant and may contain things
    # irrelevant or inappropriate to hand a candidate. [int, ...]
    knowledge_document_ids_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    candidates = relationship("Candidate", back_populates="vacancy", cascade="all, delete-orphan")
    links = relationship("VacancyLink", back_populates="vacancy", cascade="all, delete-orphan")
    strategy = relationship("HiringStrategy")

    def to_dict(self):
        import json
        deal_breakers = []
        if self.deal_breakers_json:
            try:
                deal_breakers = json.loads(self.deal_breakers_json) or []
            except Exception:
                deal_breakers = []
        custom_questions = []
        if self.custom_questions_json:
            try:
                custom_questions = json.loads(self.custom_questions_json) or []
            except Exception:
                custom_questions = []
        knowledge_document_ids = []
        if self.knowledge_document_ids_json:
            try:
                knowledge_document_ids = json.loads(self.knowledge_document_ids_json) or []
            except Exception:
                knowledge_document_ids = []
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description or "",
            "knowledge_base": self.knowledge_base or "",
            "interview_location": self.interview_location or "",
            "is_open": self.is_open,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy.name if self.strategy else None,
            "extra_instructions": self.extra_instructions or "",
            "deal_breakers": deal_breakers,
            "custom_questions": custom_questions,
            "knowledge_document_ids": knowledge_document_ids,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class VacancyTemplate(Base):
    """A saved vacancy preset, kept independent of any live Vacancy row so it
    survives closing/deleting actual vacancies — used purely to spin up a new
    vacancy "on the basis of" it later, without re-entering everything.

    Vacancy-scoped knowledge base entries can't be FK'd here (they belong to
    a real vacancy_id), so they're snapshotted as JSON instead and replayed
    into fresh KnowledgeBaseEntry rows when a vacancy is created from this template.
    """
    __tablename__ = "vacancy_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True, default="")
    interview_location = Column(String, nullable=True, default="")
    strategy_id = Column(Integer, ForeignKey("hiring_strategies.id", ondelete="SET NULL"), nullable=True)
    extra_instructions = Column(Text, nullable=True, default="")
    kb_entries_json = Column(Text, nullable=True, default="[]")  # [{"category", "question", "answer"}]
    deal_breakers_json = Column(Text, nullable=True)  # [{"label", "value"}]
    custom_questions_json = Column(Text, nullable=True)  # [str, ...]
    knowledge_document_ids_json = Column(Text, nullable=True)  # [int, ...]
    created_at = Column(DateTime, default=datetime.utcnow)

    strategy = relationship("HiringStrategy")

    def to_dict(self):
        import json
        try:
            kb_entries = json.loads(self.kb_entries_json or "[]")
        except Exception:
            kb_entries = []
        try:
            deal_breakers = json.loads(self.deal_breakers_json or "[]")
        except Exception:
            deal_breakers = []
        try:
            custom_questions = json.loads(self.custom_questions_json or "[]")
        except Exception:
            custom_questions = []
        try:
            knowledge_document_ids = json.loads(self.knowledge_document_ids_json or "[]")
        except Exception:
            knowledge_document_ids = []
        return {
            "id": self.id,
            "name": self.name,
            "title": self.title,
            "description": self.description or "",
            "interview_location": self.interview_location or "",
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy.name if self.strategy else None,
            "extra_instructions": self.extra_instructions or "",
            "kb_entries_count": len(kb_entries),
            "deal_breakers": deal_breakers,
            "custom_questions": custom_questions,
            "knowledge_document_ids": knowledge_document_ids,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vacancy_id = Column(Integer, ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True, default="")
    email = Column(String, nullable=True, default="")
    source = Column(String, nullable=False, default="manual")  # hh / avito / manual / other
    external_id = Column(String, nullable=True, index=True)    # negotiation_id / chat_id
    resume_url = Column(String, nullable=True, default="")
    photo_url = Column(String, nullable=True, default="")
    age = Column(Integer, nullable=True)
    stage = Column(String, nullable=False, default="отклик", index=True)
    notes = Column(Text, nullable=True, default="")
    last_msg_id = Column(String, nullable=True)
    telegram_chat_id = Column(String, nullable=True, default="")
    telegram_username = Column(String, nullable=True, default="")
    telegram_link_code = Column(String, nullable=True)  # уникальный код для матчинга
    follow_up_count = Column(Integer, nullable=False, default=0)
    follow_up_last_sent_at = Column(DateTime, nullable=True)
    pending_interview_date = Column(String, nullable=True)   # YYYY-MM-DD, ждёт подтверждения
    pending_interview_time = Column(String, nullable=True)   # HH:MM
    pending_interview_place = Column(String, nullable=True)
    interview_notified_at = Column(DateTime, nullable=True)  # last time admin was notified about interview
    is_paused = Column(Boolean, nullable=False, default=False)
    interview_phase = Column(String, nullable=True, default="greeting")  # structured interview phase
    # Frozen copy of the strategy's stage graph, taken the first time this
    # candidate's interview is processed — so later edits to the strategy's
    # stages (rename/delete) never disrupt a conversation already in progress.
    stages_snapshot_json = Column(Text, nullable=True)
    has_unread_hh_msg = Column(Integer, nullable=False, default=0)
    pending_decline_suggested_at = Column(DateTime, nullable=True)  # AI/follow-up suggests decline, admin decides
    # AI-generated post-interview profile (score/summary/strengths/etc, see
    # _generate_candidate_profile_inner) — persisted here so the admin can
    # view it in the UI, not just as a one-shot Telegram notification.
    profile_json = Column(Text, nullable=True)
    profile_generated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    vacancy = relationship("Vacancy", back_populates="candidates")

    def to_dict(self):
        import json
        profile = None
        if self.profile_json:
            try:
                profile = json.loads(self.profile_json)
            except Exception:
                profile = None
        return {
            "id": self.id,
            "vacancy_id": self.vacancy_id,
            "name": self.name,
            "phone": self.phone or "",
            "email": self.email or "",
            "source": self.source,
            "external_id": self.external_id,
            "resume_url": self.resume_url or "",
            "photo_url": self.photo_url or "",
            "age": self.age,
            "stage": self.stage,
            "notes": self.notes or "",
            "telegram_chat_id": self.telegram_chat_id or "",
            "telegram_username": self.telegram_username or "",
            "is_paused": bool(self.is_paused),
            "pending_decline_suggested_at": self.pending_decline_suggested_at.isoformat() if self.pending_decline_suggested_at else None,
            "profile": profile,
            "profile_generated_at": self.profile_generated_at.isoformat() if self.profile_generated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RecruitmentSource(Base):
    """Stores API credentials for hh.ru / avito per source."""
    __tablename__ = "recruitment_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False, unique=True)       # "hh" | "avito"
    # hh.ru: access_token (+ optional refresh_token)
    # avito: client_id + client_secret → access_token is auto-fetched
    client_id = Column(String, nullable=True, default="")
    client_secret = Column(String, nullable=True, default="")
    access_token = Column(String, nullable=True, default="")
    refresh_token = Column(String, nullable=True, default="")
    token_expires_at = Column(DateTime, nullable=True)
    # Info fetched after successful connect
    employer_id = Column(String, nullable=True, default="")    # hh employer_id / avito user_id
    employer_name = Column(String, nullable=True, default="")
    is_active = Column(Boolean, nullable=False, default=False)
    last_error = Column(Text, nullable=True, default="")
    sync_interval_minutes = Column(Integer, nullable=False, default=15)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    links = relationship("VacancyLink", back_populates="source_rec", cascade="all, delete-orphan")

    def to_dict(self, hide_secrets=True):
        return {
            "id": self.id,
            "source": self.source,
            "client_id": self.client_id or "",
            # never expose tokens/secrets to frontend
            "has_credentials": bool(self.access_token or self.client_secret),
            "employer_id": self.employer_id or "",
            "employer_name": self.employer_name or "",
            "is_active": self.is_active,
            "last_error": self.last_error or "",
            "sync_interval_minutes": self.sync_interval_minutes,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class VacancyLink(Base):
    """Maps one internal Vacancy to one external vacancy on hh/avito."""
    __tablename__ = "vacancy_links"
    __table_args__ = (
        UniqueConstraint("vacancy_id", "source", name="uq_vacancy_source"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    vacancy_id = Column(Integer, ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False)
    source = Column(String, nullable=False)                        # "hh" | "avito"
    source_id = Column(Integer, ForeignKey("recruitment_sources.id", ondelete="CASCADE"), nullable=False)
    external_vacancy_id = Column(String, nullable=False)
    external_vacancy_title = Column(String, nullable=True, default="")
    sync_enabled = Column(Boolean, nullable=False, default=True)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_count = Column(Integer, nullable=True, default=0)    # candidates imported in last sync
    created_at = Column(DateTime, default=datetime.utcnow)

    vacancy = relationship("Vacancy", back_populates="links")
    source_rec = relationship("RecruitmentSource", back_populates="links")

    def to_dict(self):
        return {
            "id": self.id,
            "vacancy_id": self.vacancy_id,
            "vacancy_title": self.vacancy.title if self.vacancy else "",
            "source": self.source,
            "external_vacancy_id": self.external_vacancy_id,
            "external_vacancy_title": self.external_vacancy_title or "",
            "sync_enabled": self.sync_enabled,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "last_sync_count": self.last_sync_count or 0,
        }


class TelegramMessage(Base):
    """Messages exchanged with candidates via Telegram Secretary Mode."""
    __tablename__ = "telegram_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    direction = Column(String, nullable=False)   # "in" | "out"
    text = Column(Text, nullable=False, default="")
    tg_message_id = Column(String, nullable=True)
    is_ai_escalation = Column(Integer, nullable=False, default=0)  # 1 when this is an AI escalation reply
    sent_by_ai = Column(Integer, nullable=False, default=0)        # 1 when sent by AI (not admin manually)
    created_at = Column(DateTime, default=datetime.utcnow)

    candidate = relationship("Candidate")

    def to_dict(self):
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "direction": self.direction,
            "text": self.text,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
