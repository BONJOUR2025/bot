"""Приём webhook-уведомлений Авито о новых сообщениях кандидатов.

Смысл фичи: без вебхука ответ кандидата ждёт ближайшего цикла опроса (у
рабочего аккаунта интервал 60 минут). Вебхук доставляет его за секунды,
опрос при этом остаётся включённым как подстраховка — недоставленное
уведомление Авито не повторяет, а опрос подберёт сообщение на следующем круге.

Разбор payload намеренно терпимый: конверт у Авито менялся между версиями
вебхука, и незнакомая форма должна тихо игнорироваться (опрос всё равно
подберёт), а не ронять эндпоинт.
"""
from __future__ import annotations

from app.api import avito_webhook as aw


def _v3(chat_id="u2i-abc", msg_id="m1", text="Да, в поиске", author_id="777",
        type_="text", item_id=None):
    """Конверт messenger webhook v3 — тот, что Авито шлёт сейчас."""
    value = {
        "id": msg_id,
        "chat_id": chat_id,
        "author_id": author_id,
        "created": 1786356003,
        "type": type_,
        "content": {"text": text},
    }
    if item_id is not None:
        value["item_id"] = item_id
    return {
        "id": "evt-1",
        "version": "v3",
        "timestamp": 1786356003,
        "payload": {"type": "message", "value": value},
    }


class TestPayloadParsing:
    def test_extracts_the_v3_envelope(self):
        msg = aw._extract_message(_v3())
        assert msg == {
            "chat_id": "u2i-abc",
            "message_id": "m1",
            "text": "Да, в поиске",
            "author_id": "777",
            "type": "text",
            "item_id": "",
        }

    def test_item_id_is_extracted_when_present(self):
        """Объявление отличает кандидата по вакансии от покупателя по ремонту
        обуви: подписка на мессенджер одна на весь аккаунт."""
        assert aw._extract_message(_v3(item_id=2353269952))["item_id"] == "2353269952"

    def test_missing_item_id_is_empty_not_absent(self):
        """Старые конверты его не несут — вызывающий не должен ловить KeyError."""
        assert aw._extract_message(_v3())["item_id"] == ""

    def test_accepts_a_flatter_envelope(self):
        """Более старая форма — value лежит в корне, без payload."""
        body = {"value": {"id": "m2", "chat_id": "u2i-x", "content": {"text": "Привет"}}}
        msg = aw._extract_message(body)
        assert msg["message_id"] == "m2"
        assert msg["chat_id"] == "u2i-x"
        assert msg["text"] == "Привет"

    def test_unknown_shape_returns_none_instead_of_raising(self):
        assert aw._extract_message({"что-то": "другое"}) is None
        assert aw._extract_message({}) is None

    def test_message_without_chat_or_id_is_not_actionable(self):
        assert aw._extract_message({"payload": {"value": {"id": "m1"}}}) is None
        assert aw._extract_message({"payload": {"value": {"chat_id": "u2i-a"}}}) is None

    def test_non_text_message_is_still_parsed_but_typed(self):
        """Тип отдаётся наверх, чтобы эндпоинт отсеял картинки/системные."""
        msg = aw._extract_message(_v3(type_="image", text=""))
        assert msg["type"] == "image"
        assert msg["text"] == ""


class TestIpClassification:
    """_ip_is_avito используется ТОЛЬКО для логирования, не для блокировки.

    Первый же реальный вебхук после включения пришёл с 176.114.125.109 —
    вне всех опубликованных Авито диапазонов (они задокументированы для
    вебхука откликов, а не мессенджера) — и был отвергнут, притом что опрос
    эту поломку маскировал. Поэтому фильтрация снята, охраной остаётся
    43-символьный секрет в URL.
    """

    def test_documented_ranges_recognised(self):
        assert aw._ip_is_avito("185.89.12.1") is True
        assert aw._ip_is_avito("146.158.48.10") is True
        assert aw._ip_is_avito("87.245.204.33") is True

    def test_address_outside_published_ranges(self):
        assert aw._ip_is_avito("8.8.8.8") is False
        # Реальный адрес, с которого Авито прислал первый вебхук.
        assert aw._ip_is_avito("176.114.125.109") is False

    def test_unverifiable_origin(self):
        assert aw._ip_is_avito("127.0.0.1") is None
        assert aw._ip_is_avito("192.168.1.5") is None
        assert aw._ip_is_avito(None) is None
        assert aw._ip_is_avito("не ip") is None


class TestSecretPath:
    def test_secret_is_stable_and_long(self, monkeypatch):
        store = {}

        class _FakeConfig:
            def load(self):
                return dict(store)

            def patch(self, updates):
                store.update(updates)
                return dict(store)

        monkeypatch.setattr("app.services.config_service.ConfigService", lambda: _FakeConfig())

        first = aw.get_or_create_secret()
        assert len(first) >= 32
        # Второй вызов не должен выдавать новый секрет — иначе уже
        # зарегистрированный в Авито URL мгновенно протух бы.
        assert aw.get_or_create_secret() == first

    def test_webhook_path_contains_the_secret(self, monkeypatch):
        monkeypatch.setattr(aw, "get_or_create_secret", lambda: "s3cret")
        assert aw.webhook_path() == "/api/avito/webhook/s3cret"
