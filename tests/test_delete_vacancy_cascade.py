"""Regression test for the orphaned-KnowledgeBaseEntry bug: deleting a vacancy
must also delete its scoped KB entries.

SQLite only enforces the model's ondelete="CASCADE" when PRAGMA foreign_keys=ON
is set on the connection — this app never sets it (app/db/session.py only sets
journal_mode/busy_timeout) — so relying on the declared FK action alone left
12 real orphaned rows in production after two deleted vacancies. delete_vacancy
now deletes matching KnowledgeBaseEntry rows explicitly instead.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.recruitment import Vacancy, KnowledgeBaseEntry
from app.api.recruitment import delete_vacancy


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    # Full metadata, not just Vacancy/KnowledgeBaseEntry: Vacancy has a
    # relationship to Candidate, so committing a delete touches that table too.
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _make_vacancy(db, title="Тестовая вакансия"):
    v = Vacancy(title=title)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


class TestDeleteVacancyCascade:
    def test_deleting_vacancy_deletes_its_scoped_kb_entries(self, db):
        v = _make_vacancy(db)
        db.add_all([
            KnowledgeBaseEntry(scope="vacancy", vacancy_id=v.id, question="Q1", answer="A1"),
            KnowledgeBaseEntry(scope="vacancy", vacancy_id=v.id, question="Q2", answer="A2"),
        ])
        db.commit()

        delete_vacancy(v.id, db)

        assert db.query(Vacancy).filter(Vacancy.id == v.id).first() is None
        assert db.query(KnowledgeBaseEntry).filter(KnowledgeBaseEntry.vacancy_id == v.id).count() == 0

    def test_global_scope_entries_are_unaffected(self, db):
        v = _make_vacancy(db)
        db.add(KnowledgeBaseEntry(scope="global", vacancy_id=None, question="Global Q", answer="A"))
        db.commit()

        delete_vacancy(v.id, db)

        assert db.query(KnowledgeBaseEntry).filter(KnowledgeBaseEntry.scope == "global").count() == 1

    def test_other_vacancies_kb_entries_are_unaffected(self, db):
        v1 = _make_vacancy(db, "Вакансия 1")
        v2 = _make_vacancy(db, "Вакансия 2")
        db.add_all([
            KnowledgeBaseEntry(scope="vacancy", vacancy_id=v1.id, question="Q1", answer="A1"),
            KnowledgeBaseEntry(scope="vacancy", vacancy_id=v2.id, question="Q2", answer="A2"),
        ])
        db.commit()

        delete_vacancy(v1.id, db)

        remaining = db.query(KnowledgeBaseEntry).filter(KnowledgeBaseEntry.vacancy_id == v2.id).all()
        assert len(remaining) == 1
        assert remaining[0].question == "Q2"

    def test_missing_vacancy_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            delete_vacancy(999, db)
        assert exc_info.value.status_code == 404
