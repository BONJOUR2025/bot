"""Окно вакансии сохраняет жёсткие условия и критерии для ИИ.

10.08 эти поля выпали из VacancyUpdate, и PATCH молча их отбрасывал.
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.recruitment import Vacancy
from app.api.recruitment import VacancyUpdate, update_vacancy


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    yield session
    session.close()


def test_deal_breakers_and_criteria_are_saved(db):
    v = Vacancy(title="Курьер"); db.add(v); db.commit()
    update_vacancy(v.id, VacancyUpdate(
        deal_breakers=[{"label": "Права", "value": "категория B"}, {"label": " ", "value": ""}],
        extra_instructions="  Профильный опыт: курьер  ", confirmed=True), db)
    db.refresh(v)
    assert json.loads(v.deal_breakers_json) == [{"label": "Права", "value": "категория B"}]
    assert v.extra_instructions == "Профильный опыт: курьер"


def test_criteria_need_confirmation(db):
    v = Vacancy(title="Курьер"); db.add(v); db.commit()
    with pytest.raises(HTTPException):
        update_vacancy(v.id, VacancyUpdate(extra_instructions="x"), db)
