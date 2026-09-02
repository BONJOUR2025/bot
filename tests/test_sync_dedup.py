"""Импорт не заводит вторую карточку тому же человеку.

Один кандидат, откликнувшийся на два наших объявления, получал два отклика,
два чата и две карточки — и бот вёл с ним два опроса сразу. Здесь проверяется,
что этого больше не происходит и что второй отклик становится дополнительной
перепиской существующей карточки.

БД настоящая, но в памяти: `_find_twin` делает реальные запросы, и подменять
их фейковой сессией значило бы проверять заглушку, а не поведение.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.recruitment import Base, Candidate, Vacancy
from app.services import recruitment_sync as sync
from tests.conftest import run_async


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(Vacancy(id=1, title="Мастер по ремонту обуви", quick_mode_enabled=False))
    session.commit()
    yield session
    session.close()


class _Link:
    id = 1
    vacancy_id = 1
    external_vacancy_id = "135367589"
    last_synced_at = None
    last_sync_count = 0


class _Src:
    def __init__(self, source="hh"):
        self.source = source
        self.employer_id = "21315059"


def hh_item(neg_id, resume_id, *, name="Тимофеева Анастасия", phone="", chat=None):
    return {
        "external_id": neg_id,
        "platform_chat_id": chat or f"chat-{neg_id}",
        "name": name,
        "phone": phone,
        "email": "",
        "resume_url": f"https://hh.ru/resume/{resume_id}?t={neg_id}&vacancyId=135367589",
        "resume_id": resume_id,
        "photo_url": "",
        "age": None,
        "applied_at": None,
        "notes": "",
    }


def avito_item(chat_id, *, name="Моисеев Станислав", phone=""):
    return {
        "external_id": chat_id,
        "platform_chat_id": chat_id,
        "name": name,
        "phone": phone,
        "email": "",
        "resume_url": "",
        "photo_url": "",
        "age": None,
        "applied_at": None,
        "notes": "",
    }


def sync_items(db, monkeypatch, items, source="hh"):
    async def fake_hh(token, vacancy_id):
        return items

    async def fake_avito(token, employer_id, vacancy_id):
        return items

    monkeypatch.setattr(sync, "_collect_hh", fake_hh)
    monkeypatch.setattr(sync, "_collect_avito", fake_avito)
    return run_async(sync._sync_link(db, _Src(source), _Link(), "tok"))


# ── hh: два объявления, один человек ─────────────────────────────────────

def test_two_responses_from_one_resume_make_one_card(db, monkeypatch):
    sync_items(db, monkeypatch, [
        hh_item("5496983491", "13be4637"),
        hh_item("5506528508", "13be4637"),
    ])
    db.commit()
    assert db.query(Candidate).count() == 1


def test_second_response_becomes_an_extra_chat(db, monkeypatch):
    sync_items(db, monkeypatch, [hh_item("5496983491", "13be4637")])
    db.commit()
    sync_items(db, monkeypatch, [hh_item("5506528508", "13be4637")])
    db.commit()

    c = db.query(Candidate).one()
    assert c.external_id == "5496983491"          # основной канал не поехал
    assert [ch["external_id"] for ch in c.channels()] == ["5506528508"]
    assert c.merged_from()[0]["reason"] == "resume_id"


def test_different_resumes_stay_different_people(db, monkeypatch):
    """Две «Латышевы Татьяны» на одном объявлении — разные люди с разными
    резюме. Имена не сравниваются вообще именно поэтому."""
    sync_items(db, monkeypatch, [
        hh_item("5493601499", "ab1a5abb", name="Латышева Татьяна"),
        hh_item("5493601180", "f16d5287", name="Латышева Татьяна"),
    ])
    db.commit()
    assert db.query(Candidate).count() == 2


def test_repeated_sync_does_not_grow_the_channel_list(db, monkeypatch):
    """Импорт идёт каждые 15 минут и приносит те же отклики снова."""
    items = [hh_item("5496983491", "13be4637"), hh_item("5506528508", "13be4637")]
    sync_items(db, monkeypatch, items)
    db.commit()
    sync_items(db, monkeypatch, items)
    db.commit()
    c = db.query(Candidate).one()
    assert len(c.channels()) == 1


def test_resume_id_is_stored_for_new_candidates(db, monkeypatch):
    sync_items(db, monkeypatch, [hh_item("5496983491", "13be4637")])
    db.commit()
    assert db.query(Candidate).one().resume_id == "13be4637"


def test_resume_id_is_backfilled_on_an_existing_card(db, monkeypatch):
    """Карточки, импортированные до появления колонки, иначе продолжали бы
    плодить близнецов."""
    db.add(Candidate(vacancy_id=1, name="Тимофеева Анастасия", source="hh",
                     external_id="5496983491", stage="новый", resume_id=None,
                     resume_url=""))
    db.commit()
    sync_items(db, monkeypatch, [hh_item("5496983491", "13be4637")])
    db.commit()
    assert db.query(Candidate).one().resume_id == "13be4637"


# ── между площадками: по телефону ────────────────────────────────────────

def test_hh_response_joins_an_avito_card_by_phone(db, monkeypatch):
    db.add(Candidate(vacancy_id=1, name="Моисеев Станислав", source="avito",
                     external_id="u2i-77", platform_chat_id="u2i-77",
                     stage="новый", phone="79119452719"))
    db.commit()

    sync_items(db, monkeypatch, [
        hh_item("5490000001", "aaa111", name="Моисеев Станислав",
                phone="+7 911 945-27-19"),
    ])
    db.commit()

    c = db.query(Candidate).one()
    # hh становится основным каналом: опрос должен идти через него.
    assert c.source == "hh"
    assert c.external_id == "5490000001"
    assert [(ch["source"], ch["external_id"]) for ch in c.channels()] == [("avito", "u2i-77")]
    assert c.merged_from()[0]["reason"] == "phone"


def test_avito_response_joins_an_hh_card_without_demoting_it(db, monkeypatch):
    db.add(Candidate(vacancy_id=1, name="Моисеев Станислав", source="hh",
                     external_id="5490000001", platform_chat_id="chat-1",
                     stage="новый", phone="+7 911 945-27-19"))
    db.commit()

    sync_items(db, monkeypatch, [avito_item("u2i-77", phone="79119452719")], source="avito")
    db.commit()

    c = db.query(Candidate).one()
    assert c.source == "hh"                        # основной канал остался hh
    assert [ch["source"] for ch in c.channels()] == ["avito"]


def test_no_phone_means_no_cross_platform_merge(db, monkeypatch):
    """Осознанное ограничение: без номера склеивать нечем, и лучше две
    карточки, чем склеенные разные люди."""
    db.add(Candidate(vacancy_id=1, name="Моисеев Станислав", source="avito",
                     external_id="u2i-77", platform_chat_id="u2i-77",
                     stage="новый", phone=""))
    db.commit()

    sync_items(db, monkeypatch, [hh_item("5490000001", "aaa111",
                                         name="Моисеев Станислав", phone="")])
    db.commit()
    assert db.query(Candidate).count() == 2


def test_phones_differing_only_in_format_still_match(db, monkeypatch):
    db.add(Candidate(vacancy_id=1, name="Кто-то", source="avito", external_id="u2i-1",
                     platform_chat_id="u2i-1", stage="новый", phone="8 (911) 945-27-19"))
    db.commit()
    sync_items(db, monkeypatch, [hh_item("999", "rid1", phone="+79119452719")])
    db.commit()
    assert db.query(Candidate).count() == 1


def test_empty_phone_field_never_matches_another_empty_one(db, monkeypatch):
    """Пустой ключ — это «ключа нет», а не «совпало»."""
    db.add(Candidate(vacancy_id=1, name="Первый", source="avito", external_id="u2i-1",
                     platform_chat_id="u2i-1", stage="новый", phone=""))
    db.add(Candidate(vacancy_id=1, name="Второй", source="avito", external_id="u2i-2",
                     platform_chat_id="u2i-2", stage="новый", phone=""))
    db.commit()
    sync_items(db, monkeypatch, [avito_item("u2i-3", name="Третий", phone="")],
               source="avito")
    db.commit()
    assert db.query(Candidate).count() == 3


def test_candidates_of_another_vacancy_are_not_touched(db, monkeypatch):
    db.add(Vacancy(id=2, title="Другая вакансия", quick_mode_enabled=False))
    db.add(Candidate(vacancy_id=2, name="Тимофеева Анастасия", source="hh",
                     external_id="5496983491", stage="новый", resume_id="13be4637"))
    db.commit()

    sync_items(db, monkeypatch, [hh_item("5506528508", "13be4637")])
    db.commit()
    assert db.query(Candidate).count() == 2
