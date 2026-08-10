"""Откладывание общения на нерабочие часы и продолжение цепочки.

Постановка, которую фиксируют эти тесты:
* кандидат ответил в нерабочее время → бот молчит;
* ответ НЕ теряется и НЕ обрабатывается заново с нуля;
* когда наступают рабочие часы, цепочка продолжается с места остановки;
* всё это переживает падение сервера, потому что отложенное лежит в БД
  (quick_state_json), а не в памяти процесса.
"""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from app.services import candidate_hours as ch
from app.services import quick_screening as qs
from tests.conftest import run_async

QUESTIONS = ["Есть ли опыт?", "Гражданство РФ?", "Где живёте?"]


class _FakeVacancy:
    id = 1
    title = "Мастер по ремонту обуви"
    quick_mode_enabled = True
    quick_questions_json = json.dumps(QUESTIONS, ensure_ascii=False)


class _FakeCandidate:
    def __init__(self, state=None):
        self.id = 42
        self.name = "Иван Петров"
        self.source = "hh"
        self.external_id = "neg-1"
        self.vacancy_id = 1
        self.platform_chat_id = ""
        self.is_paused = False
        self.stage = "новый"
        self.quick_state_json = json.dumps(state, ensure_ascii=False) if state else None
        self.last_message_text = ""
        self.last_message_at = None
        self.last_message_from = ""


class _FakeSource:
    source = "hh"
    employer_id = "1"


class _FakeDb:
    def commit(self):
        pass


@pytest.fixture
def closed(monkeypatch):
    """Нерабочее время."""
    monkeypatch.setattr(ch, "is_within", lambda *a, **kw: False)


@pytest.fixture
def open_hours(monkeypatch):
    monkeypatch.setattr(ch, "is_within", lambda *a, **kw: True)


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def fake_send(token, neg_id, text):
        out.append(text)
        return {}

    monkeypatch.setattr("app.services.hh_api.send_message", fake_send)
    return out


@pytest.fixture
def quiet(monkeypatch):
    async def fake_notify(text):
        return True

    monkeypatch.setattr("app.services.notify.send_notification", fake_notify)


@pytest.fixture
def no_llm(monkeypatch):
    monkeypatch.setattr("app.services.llm_client.get_client", lambda cfg: None)


def _asking(idx=0, phase="questions"):
    return {
        "status": "asking", "phase": phase, "idx": idx, "answers": [],
        "asked_at": datetime.utcnow().isoformat(), "last_msg_id": "", "silence_alerted": False,
    }


class TestReplyOutsideHours:
    def test_bot_stays_silent_and_stores_the_reply(self, closed, sent, quiet, no_llm):
        c = _FakeCandidate(_asking())
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok",
                                      "Да, есть опыт", "m1", {}))

        assert sent == []  # молчим
        state = qs.load_state(c)
        assert state["deferred_incoming"]["text"] == "Да, есть опыт"
        # Прогресс не сдвинулся — ответ ещё не засчитан.
        assert state["idx"] == 0
        assert state["answers"] == []

    def test_deferred_reply_is_marked_processed_so_polling_wont_requeue_it(self, closed, sent, quiet, no_llm):
        """Одно сообщение приходит и вебхуком, и опросом. Если не пометить
        его обработанным, опрос отложит его второй раз."""
        c = _FakeCandidate(_asking())
        db = _FakeDb()
        run_async(qs.handle_incoming(db, c, _FakeVacancy(), _FakeSource(), "tok", "Да", "m1", {}))
        run_async(qs.handle_incoming(db, c, _FakeVacancy(), _FakeSource(), "tok", "Да", "m1", {}))

        assert qs.load_state(c)["deferred_incoming"]["message_id"] == "m1"
        assert sent == []

    def test_reply_is_visible_to_the_admin_immediately(self, closed, sent, quiet, no_llm):
        """Молчит бот, а не система: в карточке ответ должен быть виден сразу."""
        c = _FakeCandidate(_asking())
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok",
                                      "Готов выйти завтра", "m1", {}))

        assert c.last_message_text == "Готов выйти завтра"
        assert c.last_message_from == "applicant"


class TestResumeWhenHoursOpen:
    def _resolver(self):
        return lambda source: (_FakeSource(), "tok")

    class _Db(_FakeDb):
        def __init__(self, candidates, vacancy):
            self._c = candidates
            self._v = vacancy

        def query(self, model):
            from app.models.recruitment import Candidate
            rows = self._c if model is Candidate else [self._v]

            class _Q:
                def filter(self, *a, **kw):
                    return self

                def all(self):
                    return rows

                def first(self):
                    return rows[0] if rows else None

            return _Q()

    def test_chain_continues_from_where_it_stopped(self, sent, quiet, no_llm, monkeypatch):
        """Главное требование: не заново, а с места остановки."""
        monkeypatch.setattr(ch, "is_within", lambda *a, **kw: False)
        c = _FakeCandidate(_asking(idx=1))  # первый вопрос уже отвечен
        c.quick_state_json = json.dumps({**_asking(idx=1),
                                          "answers": [{"q": QUESTIONS[0], "a": "Да"}]},
                                         ensure_ascii=False)
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok",
                                      "Гражданство РФ есть", "m2", {}))
        assert sent == []

        # Наступили рабочие часы — доигрываем.
        monkeypatch.setattr(ch, "is_within", lambda *a, **kw: True)
        db = self._Db([c], _FakeVacancy())
        processed = run_async(qs.flush_deferred(db, self._resolver()))

        assert processed == 1
        state = qs.load_state(c)
        assert "deferred_incoming" not in state
        # Ответ засчитан именно на второй вопрос, и задан третий — цепочка
        # продолжилась, а не началась с приветствия.
        assert [a["a"] for a in state["answers"]] == ["Да", "Гражданство РФ есть"]
        assert sent == [QUESTIONS[2]]

    def test_survives_a_restart(self, sent, quiet, no_llm, monkeypatch):
        """Падение сервера между «ответил» и «ответили»: состояние читается
        из БД, поэтому после рестарта цепочка доигрывается, а не теряется."""
        monkeypatch.setattr(ch, "is_within", lambda *a, **kw: False)
        c = _FakeCandidate(_asking())
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok",
                                      "Да, есть", "m1", {}))
        persisted = c.quick_state_json  # это всё, что переживает падение

        # Новый процесс: объект кандидата создан заново из БД.
        monkeypatch.setattr(ch, "is_within", lambda *a, **kw: True)
        revived = _FakeCandidate()
        revived.quick_state_json = persisted
        db = self._Db([revived], _FakeVacancy())

        assert run_async(qs.flush_deferred(db, self._resolver())) == 1
        assert [a["a"] for a in qs.load_state(revived)["answers"]] == ["Да, есть"]
        assert sent == [QUESTIONS[1]]

    def test_nothing_happens_while_hours_are_closed(self, sent, quiet, no_llm, closed):
        c = _FakeCandidate({**_asking(), "deferred_incoming": {"text": "Да", "message_id": "m1"}})
        db = self._Db([c], _FakeVacancy())

        assert run_async(qs.flush_deferred(db, self._resolver())) == 0
        assert sent == []


class TestNewResponseOutsideHours:
    def test_screening_is_queued_not_started(self, closed, sent, quiet):
        """Отклик в 3 ночи не должен получить приветствие в 3 ночи — но и
        потеряться не должен."""
        c = _FakeCandidate()
        ok = run_async(qs.start_screening(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok"))

        assert ok is False
        assert sent == []
        assert qs.load_state(c)["status"] == "queued"

    def test_queued_screening_starts_when_hours_open(self, sent, quiet, monkeypatch):
        monkeypatch.setattr(ch, "is_within", lambda *a, **kw: False)
        c = _FakeCandidate()
        run_async(qs.start_screening(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok"))
        assert qs.load_state(c)["status"] == "queued"

        monkeypatch.setattr(ch, "is_within", lambda *a, **kw: True)
        db = TestResumeWhenHoursOpen._Db([c], _FakeVacancy())
        processed = run_async(qs.flush_deferred(db, lambda s: (_FakeSource(), "tok")))

        assert processed == 1
        assert qs.load_state(c)["status"] == "asking"
        assert len(sent) == 1
        assert qs.INTEREST_QUESTION in sent[0]
