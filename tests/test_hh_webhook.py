"""Приём webhook-уведомлений hh.ru о новых сообщениях кандидатов.

Контракт hh (из OpenAPI-спеки, tag Webhook-API — в GitHub-доках hh их нет):

* колбэк НЕ содержит текст сообщения, только chat_id/message_id/роль/тип,
  поэтому текст всё равно дочитывается через API откликов; выигрыш — в
  моменте срабатывания, а не в экономии запросов;
* chat_id ≠ id отклика: отвечаем в negotiation (Candidate.external_id), а
  кандидата ищем по platform_chat_id;
* на дубликат ожидается 409, а не 200 — по нему hh понимает, что доставка
  засчитана; подписка, которая долго не отвечает как надо, ставится в
  очередь на блокировку;
* доставка не гарантируется — опрос остаётся подстраховкой.
"""
from __future__ import annotations

from app.api import hh_webhook as hw


def _event(action="CHAT_MESSAGE_CREATED", role="APPLICANT", mtype="SIMPLE",
           chat_id="99887766", message_id="15057795264", event_id="evt-1"):
    return {
        "id": event_id,
        "subscription_id": "sub-1",
        "action_type": action,
        "user_id": "0",
        "payload": {
            "chat_id": chat_id,
            "message_id": message_id,
            "message_type": mtype,
            "role": role,
            "sender_participant_id": "p1",
            "is_current_participant": False,
            "creation_time": "2026-08-11T00:36:13+0300",
        },
    }


class TestEventParsing:
    def test_applicant_message_is_actionable(self):
        assert hw.extract_message_event(_event()) == {
            "chat_id": "99887766",
            "message_id": "15057795264",
            "event_id": "evt-1",
        }

    def test_our_own_and_bot_messages_are_ignored(self):
        """Подписка отдаёт и наши исходящие — иначе бот ответил бы сам себе."""
        assert hw.extract_message_event(_event(role="EMPLOYER")) is None
        assert hw.extract_message_event(_event(role="BOT")) is None

    def test_service_messages_are_ignored(self):
        """PARTICIPANT_JOINED/LEFT — не ответ кандидата."""
        assert hw.extract_message_event(_event(mtype="PARTICIPANT_JOINED")) is None
        assert hw.extract_message_event(_event(mtype="PARTICIPANT_LEFT")) is None

    def test_other_event_types_are_ignored(self):
        """Подписка одна на все события: hh шлёт на тот же URL и события по
        вакансиям, реагировать на них здесь нечем."""
        assert hw.extract_message_event(_event(action="VACANCY_ARCHIVATION")) is None
        assert hw.extract_message_event(_event(action="NEW_RESPONSE_OR_INVITATION_VACANCY")) is None

    def test_incomplete_payload_is_ignored_not_raised(self):
        broken = _event()
        del broken["payload"]["chat_id"]
        assert hw.extract_message_event(broken) is None
        assert hw.extract_message_event({"action_type": "CHAT_MESSAGE_CREATED"}) is None
        assert hw.extract_message_event({}) is None
        assert hw.extract_message_event(None) is None


class TestSecret:
    def test_secret_is_stable_and_separate_from_avito(self, monkeypatch):
        store = {}

        class _FakeConfig:
            def load(self):
                return dict(store)

            def patch(self, updates):
                store.update(updates)
                return dict(store)

        monkeypatch.setattr("app.services.config_service.ConfigService", lambda: _FakeConfig())

        first = hw.get_or_create_secret()
        assert len(first) >= 32
        assert hw.get_or_create_secret() == first
        # Ключ свой: утечка одного секрета не открывает вебхук второй площадки.
        assert hw._SECRET_KEY != "avito_webhook_secret"

    def test_webhook_path_shape(self, monkeypatch):
        monkeypatch.setattr(hw, "get_or_create_secret", lambda: "s3cret")
        assert hw.webhook_path() == "/api/hh/webhook/s3cret"
