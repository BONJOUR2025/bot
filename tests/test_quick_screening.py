"""Tests for «быстрый режим» — screening a candidate in the job board's own chat.

The four alert points are the operator's actual spec, so each one is pinned:
new response, all answers collected, counter-question, 24h silence. Platform
sends and the LLM are stubbed — what matters here is the state machine and that
the bot never answers a candidate's question on its own.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from app.services import quick_screening as qs
from tests.conftest import run_async

QUESTIONS = ["Есть ли опыт?", "Гражданство РФ?", "Где живёте?"]


class _FakeVacancy:
    def __init__(self, enabled=True, questions=QUESTIONS):
        self.id = 1
        self.title = "Мастер по ремонту обуви"
        self.quick_mode_enabled = enabled
        self.quick_questions_json = json.dumps(questions, ensure_ascii=False) if questions is not None else None


class _FakeCandidate:
    def __init__(self, source="hh", chat_id="", state=None, is_paused=False, stage="новый"):
        self.id = 42
        self.name = "Иван Петров"
        self.source = source
        self.external_id = "neg-1"
        self.vacancy_id = 1
        self.platform_chat_id = chat_id
        self.quick_state_json = json.dumps(state, ensure_ascii=False) if state else None
        self.is_paused = is_paused
        self.stage = stage


class _FakeSource:
    employer_id = "21315059"


class _FakeDb:
    def commit(self):
        pass


@pytest.fixture
def alerts(monkeypatch):
    sent = []

    async def fake_send(text):
        sent.append(text)
        return True

    monkeypatch.setattr("app.services.notify.send_notification", fake_send)
    return sent


@pytest.fixture
def sent_messages(monkeypatch):
    """Capture what the bot writes to the candidate on the platform."""
    sent = []

    async def fake_hh_send(token, neg_id, text):
        sent.append(("hh", neg_id, text))
        return {}

    async def fake_avito_send(token, user_id, chat_id, text):
        sent.append(("avito", chat_id, text))
        return {}

    monkeypatch.setattr("app.services.hh_api.send_message", fake_hh_send)
    monkeypatch.setattr("app.services.avito_api.send_message", fake_avito_send)
    return sent


@pytest.fixture
def no_llm(monkeypatch):
    """Force the keyword fallback so question-detection is deterministic."""
    monkeypatch.setattr("app.services.llm_client.get_client", lambda cfg: None)


class TestQuickModeDetection:
    def test_enabled_with_questions(self):
        assert qs.is_quick_mode(_FakeVacancy()) is True

    def test_disabled_flag(self):
        assert qs.is_quick_mode(_FakeVacancy(enabled=False)) is False

    def test_enabled_but_no_questions_is_not_quick_mode(self):
        """A toggle with an empty question list would otherwise start a screen
        that immediately has nothing to ask."""
        assert qs.is_quick_mode(_FakeVacancy(questions=[])) is False

    def test_none_vacancy(self):
        assert qs.is_quick_mode(None) is False

    def test_malformed_questions_json_is_ignored(self):
        v = _FakeVacancy()
        v.quick_questions_json = "{not json"
        assert qs.get_questions(v) == []

    def test_blank_questions_are_dropped(self):
        v = _FakeVacancy(questions=["Опыт?", "   ", ""])
        assert qs.get_questions(v) == ["Опыт?"]


class TestStart:
    def test_alerts_admin_and_greets_with_interest_question(self, alerts, sent_messages):
        c, v = _FakeCandidate(), _FakeVacancy()
        ok = run_async(qs.start_screening(_FakeDb(), c, v, _FakeSource(), "tok"))

        assert ok is True
        # Уведомления на старте больше нет: их приходило по шесть в сутки,
        # и ни одно не требовало действия — бот как раз работает сам.
        assert alerts == []
        assert len(sent_messages) == 1
        assert sent_messages[0][:2] == ("hh", "neg-1")
        assert "Здравствуйте" in sent_messages[0][2]
        assert qs.INTEREST_QUESTION in sent_messages[0][2]

        state = qs.load_state(c)
        assert state["status"] == "asking"
        assert state["phase"] == "interest"
        assert state["idx"] == 0
        assert state["answers"] == []

    def test_does_not_restart_an_already_running_screen(self, alerts, sent_messages):
        c = _FakeCandidate(state={"status": "asking", "idx": 1, "answers": []})
        ok = run_async(qs.start_screening(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok"))

        assert ok is False
        assert sent_messages == []
        assert alerts == []

    def test_send_failure_hands_over_instead_of_looping(self, alerts, monkeypatch):
        async def boom(token, neg_id, text):
            raise ValueError("disabled_by_employer")

        monkeypatch.setattr("app.services.hh_api.send_message", boom)
        c = _FakeCandidate()
        ok = run_async(qs.start_screening(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok"))

        assert ok is False
        assert qs.load_state(c)["status"] == "waiting_admin"
        assert any("Не удалось написать" in a for a in alerts)

    def test_avito_without_chat_id_is_reported_not_crashed(self, alerts, sent_messages):
        """An apply of type by_call has no chat — that is data, not an error."""
        c = _FakeCandidate(source="avito", chat_id="")
        ok = run_async(qs.start_screening(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok"))

        assert ok is False
        assert sent_messages == []
        assert any("нет чата" in a for a in alerts)

    def test_avito_with_chat_id_sends_to_that_chat(self, alerts, sent_messages):
        c = _FakeCandidate(source="avito", chat_id="u2i-123-456")
        run_async(qs.start_screening(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok"))

        assert len(sent_messages) == 1
        assert sent_messages[0][:2] == ("avito", "u2i-123-456")
        assert qs.INTEREST_QUESTION in sent_messages[0][2]

    def test_paused_candidate_is_not_started(self, alerts, sent_messages):
        c = _FakeCandidate(is_paused=True)
        ok = run_async(qs.start_screening(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok"))

        assert ok is False
        assert sent_messages == []
        assert alerts == []
        assert qs.load_state(c) == {}


class TestInterestCheck:
    def _greeted(self, is_paused=False):
        return _FakeCandidate(is_paused=is_paused, state={
            "status": "asking", "phase": "interest", "idx": 0, "answers": [],
            "asked_at": datetime.utcnow().isoformat(), "last_msg_id": "", "silence_alerted": False,
        })

    def test_yes_moves_on_to_the_real_questions(self, alerts, sent_messages, no_llm):
        c = self._greeted()
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok",
                                      "Да, в поиске", "m1", {}))

        state = qs.load_state(c)
        assert state["phase"] == "questions"
        assert state["idx"] == 0
        assert state["answers"] == []
        assert sent_messages == [("hh", "neg-1", "Есть ли опыт?")]
        assert c.stage == "новый"  # untouched

    def test_no_sends_farewell_and_declines(self, alerts, sent_messages, no_llm):
        c = self._greeted()
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok",
                                      "Нет, уже нашёл работу", "m1", {}))

        state = qs.load_state(c)
        assert state["status"] == "done"
        assert sent_messages == [("hh", "neg-1", qs.DECLINE_FAREWELL)]
        assert c.stage == "отказ"
        # Бот попрощался и перевёл в «Отказ» сам — в ленте это было шумом.
        assert alerts == []

    def test_counter_question_during_interest_check_hands_over(self, alerts, sent_messages, no_llm):
        c = self._greeted()
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok",
                                      "А какая зарплата?", "m1", {}))

        state = qs.load_state(c)
        assert state["status"] == "waiting_admin"
        assert state["phase"] == "interest"
        assert sent_messages == []
        assert c.stage == "новый"  # not declined — just handed to the admin
        assert len(alerts) == 1
        assert "НУЖЕН ОТВЕТ" in alerts[0] and "Вопрос от кандидата" in alerts[0]

    def test_paused_candidate_reply_is_not_processed(self, sent_messages, no_llm):
        c = self._greeted(is_paused=True)
        state_before = qs.load_state(c)
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok",
                                      "Да, в поиске", "m1", {}))

        assert qs.load_state(c) == state_before
        assert sent_messages == []

    def test_llm_verdict_wins_over_the_keyword_fallback(self, alerts, sent_messages, monkeypatch):
        """"Не, не сейчас, а вот через месяц — да" trips the "не" keyword but is
        actually a yes; the LLM should be trusted over the blunt fallback."""
        monkeypatch.setattr("app.services.llm_client.get_client", lambda cfg: object())
        monkeypatch.setattr("app.services.llm_client.chat",
                             lambda *a, **kw: '{"still_looking": true}')
        c = self._greeted()
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok",
                                      "Не, не сейчас, а вот через месяц — да", "m1", {}))

        assert qs.load_state(c)["phase"] == "questions"
        assert c.stage == "новый"

    def test_llm_failure_falls_back_to_keywords(self, monkeypatch):
        monkeypatch.setattr("app.services.llm_client.get_client", lambda cfg: object())

        def boom(*a, **kw):
            raise RuntimeError("provider down")

        monkeypatch.setattr("app.services.llm_client.chat", boom)
        assert qs._looks_still_interested("Да, в поиске", {}) is True
        assert qs._looks_still_interested("Нет, уже не ищу", {}) is False

    def test_default_is_still_looking_on_unclear_reply(self):
        """Ambiguous text with no LLM configured must not be read as a
        decline — see _NOT_LOOKING_HINT's docstring."""
        assert qs._looks_still_interested("окей", {}) is True


class TestAnswerFlow:
    def _started(self, is_paused=False):
        return _FakeCandidate(is_paused=is_paused, state={
            "status": "asking", "idx": 0, "answers": [],
            "asked_at": datetime.utcnow().isoformat(), "last_msg_id": "", "silence_alerted": False,
        })

    def test_paused_candidate_reply_is_not_processed(self, alerts, sent_messages, no_llm):
        c = self._started(is_paused=True)
        state_before = qs.load_state(c)
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok",
                                      "Да, полтора года чинил обувь", "m1", {}))

        assert qs.load_state(c) == state_before  # untouched — admin handles it manually
        assert sent_messages == []
        assert alerts == []

    def test_answer_advances_to_next_question(self, alerts, sent_messages, no_llm):
        c = self._started()
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok",
                                      "Да, полтора года чинил обувь", "m1", {}))

        state = qs.load_state(c)
        assert state["idx"] == 1
        assert state["answers"] == [{"q": "Есть ли опыт?", "a": "Да, полтора года чинил обувь"}]
        assert sent_messages == [("hh", "neg-1", "Гражданство РФ?")]
        assert alerts == []  # no alert until the end

    def test_full_run_alerts_once_with_every_answer(self, alerts, sent_messages, no_llm):
        c = self._started()
        v, src, db = _FakeVacancy(), _FakeSource(), _FakeDb()

        for i, answer in enumerate(["Да, есть", "Да, РФ", "Метро Лесная"]):
            run_async(qs.handle_incoming(db, c, v, src, "tok", answer, f"m{i}", {}))

        assert qs.load_state(c)["status"] == "done"
        assert len(alerts) == 1
        assert "НУЖЕН ОТВЕТ" in alerts[0] and "Анкета готова" in alerts[0]
        for answer in ["Да, есть", "Да, РФ", "Метро Лесная"]:
            assert answer in alerts[0]
        # two follow-up questions plus the closing message to the candidate
        assert len(sent_messages) == 3
        assert sent_messages[-1][2] == qs.CLOSING_MESSAGE

    def test_duplicate_message_id_is_ignored(self, alerts, sent_messages, no_llm):
        """The sync polls repeatedly; the same message must not double-advance."""
        c = self._started()
        v, src, db = _FakeVacancy(), _FakeSource(), _FakeDb()

        run_async(qs.handle_incoming(db, c, v, src, "tok", "Да, есть", "m1", {}))
        run_async(qs.handle_incoming(db, c, v, src, "tok", "Да, есть", "m1", {}))

        assert qs.load_state(c)["idx"] == 1
        assert len(sent_messages) == 1

    def test_empty_message_does_not_advance(self, sent_messages, no_llm):
        c = self._started()
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok", "   ", "m1", {}))

        assert qs.load_state(c)["idx"] == 0
        assert sent_messages == []

    def test_messages_ignored_once_handed_to_admin(self, alerts, sent_messages, no_llm):
        c = _FakeCandidate(state={"status": "waiting_admin", "idx": 1, "answers": []})
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok",
                                      "ещё сообщение", "m9", {}))

        assert sent_messages == []
        assert alerts == []


class TestCounterQuestion:
    def _started(self):
        return _FakeCandidate(state={
            "status": "asking", "idx": 0, "answers": [],
            "asked_at": datetime.utcnow().isoformat(), "last_msg_id": "", "silence_alerted": False,
        })

    def test_question_stops_the_bot_and_alerts(self, alerts, sent_messages, no_llm):
        c = self._started()
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok",
                                      "А какая зарплата?", "m1", {}))

        assert qs.load_state(c)["status"] == "waiting_admin"
        assert sent_messages == []  # the bot must NOT answer it
        assert len(alerts) == 1
        assert "НУЖЕН ОТВЕТ" in alerts[0] and "Вопрос от кандидата" in alerts[0]
        assert "А какая зарплата?" in alerts[0]

    def test_question_without_question_mark_is_still_caught(self, alerts, sent_messages, no_llm):
        """Russian replies often drop the "?" — "сколько платите" is a question."""
        c = self._started()
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok",
                                      "сколько платите", "m1", {}))

        assert qs.load_state(c)["status"] == "waiting_admin"
        assert sent_messages == []

    def test_alert_includes_answers_collected_so_far(self, alerts, no_llm):
        c = _FakeCandidate(state={
            "status": "asking", "idx": 1,
            "answers": [{"q": "Есть ли опыт?", "a": "Да, два года"}],
            "asked_at": datetime.utcnow().isoformat(), "last_msg_id": "", "silence_alerted": False,
        })
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok",
                                      "А где офис?", "m2", {}))

        assert "Да, два года" in alerts[0]

    def test_llm_verdict_wins_over_the_keyword_fallback(self, alerts, sent_messages, monkeypatch):
        """A plain answer that trips the keyword gate ("как раз...") must not
        be misread as a question when the LLM is available to judge."""
        monkeypatch.setattr("app.services.llm_client.get_client", lambda cfg: object())
        monkeypatch.setattr("app.services.llm_client.chat",
                            lambda *a, **kw: '{"question": false}')
        c = self._started()
        run_async(qs.handle_incoming(_FakeDb(), c, _FakeVacancy(), _FakeSource(), "tok",
                                      "Как раз работал в мастерской", "m1", {}))

        assert qs.load_state(c)["status"] == "asking"
        assert len(sent_messages) == 1

    def test_llm_failure_falls_back_to_keywords(self, monkeypatch):
        monkeypatch.setattr("app.services.llm_client.get_client", lambda cfg: object())

        def boom(*a, **kw):
            raise RuntimeError("provider down")

        monkeypatch.setattr("app.services.llm_client.chat", boom)
        assert qs._looks_like_question("А какая зарплата?", {}) is True
        assert qs._looks_like_question("Да, есть опыт", {}) is False


class TestSilence:
    class _Query:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *a, **kw):
            return self

        def all(self):
            return self._rows

        def first(self):
            return self._rows[0] if self._rows else None

    class _Db:
        def __init__(self, candidates, vacancy):
            self._candidates = candidates
            self._vacancy = vacancy

        def query(self, model):
            from app.models.recruitment import Candidate
            if model is Candidate:
                return TestSilence._Query(self._candidates)
            return TestSilence._Query([self._vacancy])

        def commit(self):
            pass

    def _candidate(self, hours_ago, silence_alerted=False, status="asking"):
        return _FakeCandidate(state={
            "status": status, "idx": 1,
            "answers": [{"q": "Есть ли опыт?", "a": "Да"}],
            "asked_at": (datetime.utcnow() - timedelta(hours=hours_ago)).isoformat(),
            "last_msg_id": "m1", "silence_alerted": silence_alerted,
        })

    def test_alerts_after_24h(self, alerts):
        c = self._candidate(hours_ago=25)
        run_async(qs.check_silence(self._Db([c], _FakeVacancy())))

        assert len(alerts) == 1
        # Молчащих за сутки бывает сразу несколько, поэтому теперь одно
        # сводное сообщение со списком, а не по уведомлению на каждого.
        assert "Молчат сутки" in alerts[0]
        assert qs.load_state(c)["silence_alerted"] is True

    def test_no_alert_before_24h(self, alerts):
        run_async(qs.check_silence(self._Db([self._candidate(hours_ago=5)], _FakeVacancy())))
        assert alerts == []

    def test_alerts_only_once(self, alerts):
        c = self._candidate(hours_ago=48, silence_alerted=True)
        run_async(qs.check_silence(self._Db([c], _FakeVacancy())))
        assert alerts == []

    def test_finished_screens_are_not_chased(self, alerts):
        c = self._candidate(hours_ago=48, status="done")
        run_async(qs.check_silence(self._Db([c], _FakeVacancy())))
        assert alerts == []

    def test_handed_over_screens_are_not_chased(self, alerts):
        """Already waiting on the admin — nagging about candidate silence there
        would be blaming the candidate for our own pending reply."""
        c = self._candidate(hours_ago=48, status="waiting_admin")
        run_async(qs.check_silence(self._Db([c], _FakeVacancy())))
        assert alerts == []

    def test_paused_candidates_are_not_chased(self, alerts):
        c = self._candidate(hours_ago=48)
        c.is_paused = True
        run_async(qs.check_silence(self._Db([c], _FakeVacancy())))
        assert alerts == []

    def test_silent_during_interest_check_names_the_interest_question(self, alerts):
        c = _FakeCandidate(state={
            "status": "asking", "phase": "interest", "idx": 0, "answers": [],
            "asked_at": (datetime.utcnow() - timedelta(hours=25)).isoformat(),
            "last_msg_id": "", "silence_alerted": False,
        })
        run_async(qs.check_silence(self._Db([c], _FakeVacancy())))

        assert len(alerts) == 1
        assert qs.INTEREST_QUESTION in alerts[0]
