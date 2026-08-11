"""Сообщения кандидату, которые инициирует человек: недозвон и отказ.

Главное обещание этого кода — **попытка дозвона фиксируется всегда**, даже
если писать некуда или площадка отвергла отправку. Как раз тем, кому звонят,
чата может не быть вовсе (отклик Авито «by_call» — только телефон), и если
учёт звонков падает вместе с отправкой, кнопка бесполезна ровно там, где
нужнее всего.
"""
from __future__ import annotations

import pytest

from app.services import candidate_outreach as outreach
from tests.conftest import run_async


class _Cand:
    def __init__(self, source="avito", chat="u2i-abc", external_id="neg-1", count=0):
        self.id = 7
        self.source = source
        self.platform_chat_id = chat
        self.external_id = external_id
        self.follow_up_count = count
        self.follow_up_last_sent_at = None
        self.last_message_text = ""
        self.last_message_at = None
        self.last_message_from = ""


class _Db:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class _Src:
    employer_id = "21315059"


class TestHasChat:
    def test_avito_with_chat(self):
        assert outreach.has_chat(_Cand()) is True

    def test_avito_by_call_has_no_chat(self):
        """Кандидат оставил только телефон — писать некуда."""
        assert outreach.has_chat(_Cand(chat="")) is False

    def test_hh_is_addressed_by_negotiation(self):
        assert outreach.has_chat(_Cand(source="hh", chat="")) is True
        assert outreach.has_chat(_Cand(source="hh", chat="", external_id=None)) is False

    def test_manual_candidate_has_no_chat(self):
        assert outreach.has_chat(_Cand(source="manual")) is False


class TestCallAttempts:
    def test_first_attempt(self):
        c, db = _Cand(), _Db()
        assert outreach.register_call_attempt(db, c) == 1
        assert c.follow_up_last_sent_at is not None
        assert db.commits == 1

    def test_attempts_accumulate(self):
        c, db = _Cand(count=2), _Db()
        assert outreach.register_call_attempt(db, c) == 3

    def test_null_counter_is_treated_as_zero(self):
        """У старых строк в колонке может лежать NULL."""
        c, db = _Cand(), _Db()
        c.follow_up_count = None
        assert outreach.register_call_attempt(db, c) == 1

    def test_reaching_the_candidate_clears_everything(self):
        c, db = _Cand(count=4), _Db()
        outreach.register_call_attempt(db, c)
        outreach.reset_call_attempts(db, c)
        assert c.follow_up_count == 0
        assert c.follow_up_last_sent_at is None


class TestSending:
    def test_avito_goes_to_the_chat_id(self, monkeypatch):
        sent = {}

        async def fake(token, user_id, chat_id, text):
            sent.update(chat_id=chat_id, text=text)

        monkeypatch.setattr("app.services.avito_api.send_message", fake)
        c, db = _Cand(), _Db()
        run_async(outreach.send_to_candidate(db, c, _Src(), "tok", "Когда удобно?"))

        assert sent == {"chat_id": "u2i-abc", "text": "Когда удобно?"}

    def test_hh_goes_to_the_negotiation(self, monkeypatch):
        sent = {}

        async def fake(token, neg_id, text):
            sent.update(neg=neg_id, text=text)

        monkeypatch.setattr("app.services.hh_api.send_message", fake)
        c, db = _Cand(source="hh"), _Db()
        run_async(outreach.send_to_candidate(db, c, _Src(), "tok", "Когда удобно?"))

        assert sent == {"neg": "neg-1", "text": "Когда удобно?"}

    def test_sent_message_shows_up_on_the_card(self, monkeypatch):
        """Иначе в воронке карточка выглядит нетронутой, хотя мы уже написали."""
        async def fake(token, user_id, chat_id, text):
            return {}

        monkeypatch.setattr("app.services.avito_api.send_message", fake)
        c, db = _Cand(), _Db()
        run_async(outreach.send_to_candidate(db, c, _Src(), "tok", "Когда удобно?"))

        assert c.last_message_text == "Когда удобно?"
        assert c.last_message_from == "employer"

    def test_empty_text_is_refused(self):
        with pytest.raises(ValueError):
            run_async(outreach.send_to_candidate(_Db(), _Cand(), _Src(), "tok", "   "))

    def test_platform_failure_propagates(self, monkeypatch):
        """Молча проглотить ошибку нельзя: «отправлено» без отправки хуже
        честной ошибки — рекрутёр перестанет звонить, а кандидат ничего не
        получит."""
        async def boom(*a, **kw):
            raise RuntimeError("403 Forbidden")

        monkeypatch.setattr("app.services.avito_api.send_message", boom)
        with pytest.raises(RuntimeError):
            run_async(outreach.send_to_candidate(_Db(), _Cand(), _Src(), "tok", "текст"))

    def test_attempt_survives_a_failed_send(self, monkeypatch):
        """Ровно тот порядок, что и в эндпоинте: сначала учёт, потом отправка.
        Упавшая отправка не должна стирать факт звонка."""
        async def boom(*a, **kw):
            raise RuntimeError("нет доступа")

        monkeypatch.setattr("app.services.avito_api.send_message", boom)
        c, db = _Cand(), _Db()
        outreach.register_call_attempt(db, c)
        with pytest.raises(RuntimeError):
            run_async(outreach.send_to_candidate(db, c, _Src(), "tok", "текст"))

        assert c.follow_up_count == 1
