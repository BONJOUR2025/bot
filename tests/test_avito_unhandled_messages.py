"""Сообщения кандидата Авито, которые не забирает опрос.

Найдено в бою. «Опрос закончен» не значит «разговор закончен»: человек
отвечает на приглашение, пишет «когда удобно», уточняет адрес. У hh такое
сообщение с самого начала уходило админу уведомлением, а в авито-ветке
вызова уведомления не было вовсе — ни одной строки кода. Сообщение
оседало в карточке, о которой никто не знал.

Стоило это пяти кандидатов за полдня, включая тех, кому мы сами написали
«когда вам удобно поговорить?» и не ответили на ответ.
"""
from __future__ import annotations

import json

import pytest

from app.services import quick_screening, recruitment_stages as rs, recruitment_sync
from tests.conftest import run_async


class _Candidate:
    def __init__(self, cid=1, name="Бугай Егор", state=None, last_msg_id=None):
        self.id = cid
        self.name = name
        self.source = "avito"
        self.platform_chat_id = "u2i-abc"
        self.stage = rs.STAGE_NEW
        self.last_msg_id = last_msg_id
        self.quick_state_json = json.dumps(state, ensure_ascii=False) if state else None


class TestWhoGetsPolled:
    """Раньше здесь стояло жёсткое «только asking», и половина живых
    разговоров была невидима."""

    def test_finished_screen_is_polled(self):
        assert recruitment_sync.should_poll_messages(_Candidate(state={"status": "done"})) is True

    def test_running_screen_is_polled(self):
        assert recruitment_sync.should_poll_messages(_Candidate(state={"status": "asking"})) is True

    def test_manual_conversation_is_polled(self):
        assert recruitment_sync.should_poll_messages(_Candidate()) is True

    def test_intermediate_states_are_skipped(self):
        for st in ("queued", "waiting_admin"):
            assert recruitment_sync.should_poll_messages(_Candidate(state={"status": st})) is False


class TestNotification:
    @pytest.fixture
    def sent(self, monkeypatch):
        out = []

        async def fake(text):
            out.append(text)
            return True

        monkeypatch.setattr("app.services.notify.send_notification", fake)
        return out

    @pytest.fixture
    def db(self, monkeypatch):
        """Подменяем сессию одним кандидатом в памяти."""
        cand = _Candidate()

        class _Session:
            def query(self, model):
                class _Q:
                    def filter(self, *a, **kw):
                        return self

                    def first(self_inner):
                        return cand
                return _Q()

            def commit(self):
                pass

            def close(self):
                pass

        monkeypatch.setattr("app.db.session.SessionLocal", lambda: _Session())
        return cand

    def test_message_reaches_the_admin(self, sent, db):
        ok = run_async(recruitment_sync.notify_unhandled_message(
            1, "Бугай Егор", "Завтра в 14:00", "m1", "avito"))

        assert ok is True
        assert "Бугай Егор" in sent[0]
        assert "Завтра в 14:00" in sent[0]
        assert "Авито" in sent[0]

    def test_the_same_message_is_not_reported_twice(self, sent, db):
        """Одно сообщение приходит и вебхуком, и опросом."""
        run_async(recruitment_sync.notify_unhandled_message(1, "Бугай Егор", "Завтра", "m1", "avito"))
        run_async(recruitment_sync.notify_unhandled_message(1, "Бугай Егор", "Завтра", "m1", "avito"))

        assert len(sent) == 1

    def test_a_newer_message_is_reported(self, sent, db):
        run_async(recruitment_sync.notify_unhandled_message(1, "Бугай Егор", "Завтра", "m1", "avito"))
        run_async(recruitment_sync.notify_unhandled_message(1, "Бугай Егор", "Уже подъезжаю", "m2", "avito"))

        assert len(sent) == 2

    def test_marked_before_sending_so_a_failed_send_cannot_loop(self, sent, db, monkeypatch):
        """Пометка ставится ДО отправки: иначе упавший Telegram означал бы
        повторное уведомление на каждом цикле опроса."""
        async def boom(text):
            raise RuntimeError("telegram down")

        monkeypatch.setattr("app.services.notify.send_notification", boom)
        with pytest.raises(RuntimeError):
            run_async(recruitment_sync.notify_unhandled_message(1, "Бугай", "Завтра", "m1", "avito"))

        assert db.last_msg_id == "m1"

    def test_empty_text_is_not_reported(self, sent, db):
        """Картинка или системное сообщение — дёргать админа не за чем."""
        assert run_async(recruitment_sync.notify_unhandled_message(
            1, "Бугай", "   ", "m1", "avito")) is False
        assert sent == []

    def test_label_matches_the_platform(self, sent, db):
        run_async(recruitment_sync.notify_unhandled_message(1, "Кто-то", "текст", "m9", "hh"))
        assert "hh.ru" in sent[0]
