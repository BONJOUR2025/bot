"""Comprehensive tests for MessageRepository."""

import json
from pathlib import Path

import pytest

from app.data.message_repository import MessageRepository
from tests.conftest import make_message_dict


def _make_repo(tmp_path, data=None):
    p = tmp_path / "messages.json"
    if data is None:
        data = [make_message_dict("1"), make_message_dict("2", user_id="200",
                timestamp="2025-01-16T11:00:00")]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return MessageRepository(path=p)


class TestMessageRepositoryInit:
    def test_loads_messages(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert len(repo.list()) == 2

    def test_empty_file(self, tmp_path):
        p = tmp_path / "messages.json"
        p.write_text("[]", encoding="utf-8")
        repo = MessageRepository(path=p)
        assert repo.list() == []

    def test_missing_file(self, tmp_path):
        p = tmp_path / "nonexistent.json"
        repo = MessageRepository(path=p)
        assert repo.list() == []


class TestMessageList:
    def test_sorted_by_timestamp_desc(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.list()
        timestamps = [r.get("timestamp", "") for r in result]
        assert timestamps == sorted(timestamps, reverse=True)


class TestMessageCreate:
    def test_create_assigns_id(self, tmp_path):
        repo = _make_repo(tmp_path, data=[])
        created = repo.create({
            "user_id": "1", "name": "Test", "text": "Hello",
            "status": "Отправлено", "accepted": False,
            "timestamp": "2025-01-15T10:00:00", "message_id": 100,
        })
        assert "id" in created

    def test_create_appends(self, tmp_path):
        repo = _make_repo(tmp_path, data=[])
        repo.create({"user_id": "1", "text": "A", "timestamp": "2025-01-01T00:00:00"})
        repo.create({"user_id": "2", "text": "B", "timestamp": "2025-01-02T00:00:00"})
        assert len(repo.list()) == 2

    def test_create_persists(self, tmp_path):
        p = tmp_path / "messages.json"
        p.write_text("[]", encoding="utf-8")
        repo = MessageRepository(path=p)
        repo.create({"user_id": "1", "text": "Hi"})
        raw = json.loads(p.read_text(encoding="utf-8"))
        assert len(raw) == 1


class TestMessageAccept:
    def test_accept_by_id(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.accept("1")
        assert result is not None
        assert result["accepted"] is True
        assert result["status"] == "Принято"
        assert "timestamp_accept" in result

    def test_accept_nonexistent(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert repo.accept("999") is None

    def test_accept_by_details(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.accept_by_details("100", 12345)
        assert result is not None
        assert result["accepted"] is True

    def test_accept_by_details_not_found(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert repo.accept_by_details("999", 99999) is None

    def test_accept_persists(self, tmp_path):
        p = tmp_path / "messages.json"
        data = [make_message_dict("1")]
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        repo = MessageRepository(path=p)
        repo.accept("1")
        raw = json.loads(p.read_text(encoding="utf-8"))
        assert raw[0]["accepted"] is True
