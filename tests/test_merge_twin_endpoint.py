"""Склейка откликов одного человека на разные вакансии — через эндпоинт, на реальной схеме."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.recruitment import Candidate, TelegramMessage, Vacancy
from app.api.recruitment import MergeTwinRequest, merge_twin
from app.services import candidate_merge as cm


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    yield session
    session.close()
    engine.dispose()


def _pair(db):
    a, b = Vacancy(title="Охта Молл"), Vacancy(title="Академ Парк")
    db.add_all([a, b]); db.commit()
    c1 = Candidate(vacancy_id=a.id, name="Анна", source="hh", external_id="neg-1",
                   resume_id="r1", stage="новый")
    c2 = Candidate(vacancy_id=b.id, name="Анна", source="hh", external_id="neg-2",
                   resume_id="r1", stage="отказ")
    db.add_all([c1, c2]); db.commit()
    return a, b, c1, c2


def test_merge_keeps_primary_and_absorbs_other(db):
    a, b, c1, c2 = _pair(db)
    db.add(TelegramMessage(candidate_id=c2.id, direction="in", text="привет")); db.commit()
    c2_id = c2.id

    res = merge_twin(c1.id, MergeTwinRequest(twin_id=c2_id, primary_vacancy_id=b.id), db)

    assert res == {"id": c2_id, "vacancy_id": b.id}
    assert db.query(Candidate).count() == 1
    winner = db.get(Candidate, c2_id)
    assert winner.stage == "отказ"  # решение по основной точке не трогаем
    assert winner.merged_from()[-1]["vacancy_title"] == "Охта Молл"
    assert db.query(TelegramMessage).filter(TelegramMessage.candidate_id == c2_id).count() == 1
    # Синк найдёт отклик второй вакансии среди каналов и не заведёт его заново.
    assert cm.find_absorbed(db, "hh", "neg-1").id == c2_id


def test_primary_must_be_one_of_the_two(db):
    a, b, c1, c2 = _pair(db)
    other = Vacancy(title="Озерки"); db.add(other); db.commit()
    with pytest.raises(HTTPException) as e:
        merge_twin(c1.id, MergeTwinRequest(twin_id=c2.id, primary_vacancy_id=other.id), db)
    assert e.value.status_code == 400


def test_refuses_different_people(db):
    a, b, c1, c2 = _pair(db)
    c2.resume_id = "r2"; db.commit()
    with pytest.raises(HTTPException) as e:
        merge_twin(c1.id, MergeTwinRequest(twin_id=c2.id, primary_vacancy_id=a.id), db)
    assert e.value.status_code == 400
