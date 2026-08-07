"""The first sync of a vacancy link must not message the existing backlog.

Connecting Avito imports every open chat on the vacancy as a candidate — 76
real people on the live account when this was written. Starting the screening
bot on all of them because the integration happened to be switched on today
would send unsolicited messages to strangers, so the first pass only records
them and screening begins with genuinely new arrivals.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.services import recruitment_sync as sync
from tests.conftest import run_async


class _FakeLink:
    def __init__(self, last_synced_at=None):
        self.id = 1
        self.vacancy_id = 1
        self.external_vacancy_id = "2353269952"
        self.last_synced_at = last_synced_at
        self.last_sync_count = 0
        self.sync_enabled = True


class _FakeVacancy:
    id = 1
    title = "Мастер по ремонту обуви"
    quick_mode_enabled = True
    quick_questions_json = '["Есть ли опыт?", "Гражданство РФ?"]'


class _FakeSource:
    source = "avito"
    employer_id = "21315059"


class _FakeCandidate:
    def __init__(self, cand_id, external_id):
        self.id = cand_id
        self.name = f"Кандидат {cand_id}"
        self.source = "avito"
        self.external_id = external_id
        self.vacancy_id = 1
        self.platform_chat_id = external_id
        self.quick_state_json = None


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *a, **kw):
        return self

    def first(self):
        return self._result

    def all(self):
        return self._result if isinstance(self._result, list) else []


class _FakeDb:
    """Reports no pre-existing candidates, so every collected item is new."""

    def __init__(self, vacancy):
        self._vacancy = vacancy
        self.added = []

    def query(self, model):
        from app.models.recruitment import Vacancy
        if model is Vacancy:
            return _FakeQuery(self._vacancy)
        return _FakeQuery(None)  # Candidate lookup → nothing exists yet

    def add(self, obj):
        obj.id = len(self.added) + 1
        self.added.append(obj)

    def flush(self):
        pass

    def commit(self):
        pass


@pytest.fixture
def collected(monkeypatch):
    """Three applicants arriving from Avito."""
    async def fake_collect(token, employer_id, vacancy_id):
        return [
            {"external_id": f"u2i-{i}", "name": f"Кандидат {i}", "phone": "", "email": "",
             "resume_url": "", "age": None, "notes": "", "platform_chat_id": f"u2i-{i}",
             "applied_at": None}
            for i in range(3)
        ]

    monkeypatch.setattr(sync, "_collect_avito", fake_collect)


@pytest.fixture
def started(monkeypatch):
    calls = []

    async def fake_start(db, candidate, vacancy, src, token):
        calls.append(candidate.external_id)
        return True

    monkeypatch.setattr("app.services.quick_screening.start_screening", fake_start)
    return calls


@pytest.fixture
def quiet_notify(monkeypatch):
    async def fake_send(text):
        return True

    monkeypatch.setattr("app.services.notify.send_notification", fake_send)


def test_first_sync_imports_without_messaging_anyone(collected, started, quiet_notify):
    db = _FakeDb(_FakeVacancy())
    link = _FakeLink(last_synced_at=None)

    result = run_async(sync._sync_link(db, _FakeSource(), link, "tok"))

    assert len(result) == 3           # all imported
    assert len(db.added) == 3
    assert started == []              # ...and nobody was written to


def test_later_syncs_do_screen_new_arrivals(collected, started, quiet_notify):
    db = _FakeDb(_FakeVacancy())
    link = _FakeLink(last_synced_at=datetime.utcnow())

    run_async(sync._sync_link(db, _FakeSource(), link, "tok"))

    assert started == ["u2i-0", "u2i-1", "u2i-2"]


def test_quick_mode_off_leaves_the_old_telegram_flow_alone(collected, started, quiet_notify, monkeypatch):
    triggered = []

    async def fake_trigger(cid, force=False):
        triggered.append(cid)
        return "ok"

    monkeypatch.setattr("app.services.automation.is_enabled", lambda: True)
    monkeypatch.setattr("app.services.automation.trigger_for_candidate", fake_trigger)

    vacancy = _FakeVacancy()
    vacancy.quick_mode_enabled = False
    db = _FakeDb(vacancy)

    run_async(sync._sync_link(db, _FakeSource(), _FakeLink(last_synced_at=datetime.utcnow()), "tok"))

    assert started == []  # quick screening stays out of it
