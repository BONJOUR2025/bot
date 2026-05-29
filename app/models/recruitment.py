from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.base_class import Base


class Vacancy(Base):
    __tablename__ = "vacancies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True, default="")
    knowledge_base = Column(Text, nullable=True, default="")
    interview_location = Column(String, nullable=True, default="")
    is_open = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    candidates = relationship("Candidate", back_populates="vacancy", cascade="all, delete-orphan")
    links = relationship("VacancyLink", back_populates="vacancy", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description or "",
            "knowledge_base": self.knowledge_base or "",
            "interview_location": self.interview_location or "",
            "is_open": self.is_open,
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
    follow_up_count = Column(Integer, nullable=False, default=0)          # 0→1→2→3(notified)
    follow_up_last_sent_at = Column(DateTime, nullable=True)              # UTC timestamp of last follow-up
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    vacancy = relationship("Vacancy", back_populates="candidates")

    def to_dict(self):
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


class UnlinkedTelegramMessage(Base):
    __tablename__ = "unlinked_telegram_messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String, nullable=False)
    sender_name = Column(String, nullable=True, default="")
    text = Column(Text, nullable=False, default="")
    tg_message_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "sender_name": self.sender_name or "",
            "text": self.text,
            "created_at": self.created_at.isoformat() if self.created_at else None,
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
