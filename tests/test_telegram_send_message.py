from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.telegram import create_telegram_router, TelegramService


def test_send_message_accepts_photo_url(monkeypatch):
    async def fake_send_message_to_user(self, user_id, message, parse_mode="HTML", photo_url=None, require_ack=False):
        assert photo_url == "http://example.com/pic.jpg"
        return 123

    monkeypatch.setattr(TelegramService, "send_message_to_user", fake_send_message_to_user)

    repo = SimpleNamespace()
    app = FastAPI()
    app.include_router(create_telegram_router(repo))
    client = TestClient(app)

    payload = {"user_id": "1", "message": "hi", "photo_url": "http://example.com/pic.jpg"}
    resp = client.post("/telegram/send_message", json=payload)
    assert resp.status_code == 200
    assert resp.json()["message_id"] == 123


def test_send_message_without_photo(monkeypatch):
    async def fake_send_message_to_user(self, user_id, message, parse_mode="HTML", photo_url=None, require_ack=False):
        assert photo_url is None
        return 42

    monkeypatch.setattr(TelegramService, "send_message_to_user", fake_send_message_to_user)

    repo = SimpleNamespace()
    app = FastAPI()
    app.include_router(create_telegram_router(repo))
    client = TestClient(app)

    payload = {"user_id": "1", "message": "hi"}
    resp = client.post("/telegram/send_message", json=payload)
    assert resp.status_code == 200
    assert resp.json()["message_id"] == 42
