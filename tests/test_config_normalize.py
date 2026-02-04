"""Tests for config.py normalization helpers."""

from app.config import _normalize_card_dispatch_chats


class TestNormalizeCardDispatchChats:
    def test_valid_entries(self):
        raw = [
            {"key": "default", "name": "Кассир 1", "chat_id": -100123},
            {"key": "second", "name": "Кассир 2", "chat_id": -100456},
        ]
        result = _normalize_card_dispatch_chats(raw, None)
        assert len(result) == 2
        assert result[0]["key"] == "default"
        assert result[1]["chat_id"] == -100456

    def test_entries_with_missing_key(self):
        raw = [{"name": "Кассир", "chat_id": -100123}]
        result = _normalize_card_dispatch_chats(raw, None)
        assert len(result) == 1
        assert result[0]["key"] == "chat_1"

    def test_entries_with_invalid_chat_id(self):
        raw = [{"key": "bad", "name": "Bad", "chat_id": "not_a_number"}]
        result = _normalize_card_dispatch_chats(raw, None)
        assert len(result) == 0

    def test_non_dict_entries_skipped(self):
        raw = ["not a dict", {"key": "ok", "name": "OK", "chat_id": -100}]
        result = _normalize_card_dispatch_chats(raw, None)
        assert len(result) == 1

    def test_empty_list_with_fallback(self):
        result = _normalize_card_dispatch_chats([], -999)
        assert len(result) == 1
        assert result[0]["key"] == "default"
        assert result[0]["chat_id"] == -999

    def test_none_with_fallback(self):
        result = _normalize_card_dispatch_chats(None, -111)
        assert len(result) == 1

    def test_empty_no_fallback(self):
        result = _normalize_card_dispatch_chats([], None)
        assert len(result) == 0

    def test_fallback_invalid_value(self):
        result = _normalize_card_dispatch_chats([], "invalid")
        assert len(result) == 0
