"""Tests for API telegram endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.telegram import create_telegram_router
from app.api.dependencies import get_current_user
from app.services.access_control_service import ResolvedUser
from app.services.telegram_service import (
    TelegramAPIError,
    TelegramNotConfiguredError,
    InvalidTelegramUserIdError,
)


def _resolved():
    return ResolvedUser(
        id="admin", login="admin", role_id="owner", role_name="Owner",
        permissions=["*"], bot_buttons=["*"], display_name="Admin",
        allowed_employee_ids=None, allowed_departments=None,
    )


def _make_app(bot_configured=True):
    repo = MagicMock()
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: _resolved()

    with patch("app.api.telegram.TelegramService") as MockTgSvc:
        svc_instance = AsyncMock()
        svc_instance.bot = MagicMock() if bot_configured else None
        svc_instance._load_log.return_value = []
        MockTgSvc.return_value = svc_instance
        router = create_telegram_router(repo)
        app.include_router(router, prefix="/api")
        return TestClient(app), svc_instance


class TestSendMessage:
    def test_send_success(self):
        c, svc = _make_app()
        svc.send_message_to_user.return_value = 42
        resp = c.post("/api/telegram/send_message", json={
            "user_id": "100", "message": "Hello",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["message_id"] == 42

    def test_send_bot_not_configured(self):
        c, svc = _make_app(bot_configured=False)
        resp = c.post("/api/telegram/send_message", json={
            "user_id": "100", "message": "Hello",
        })
        assert resp.status_code == 400

    def test_send_invalid_user_id(self):
        c, svc = _make_app()
        svc.send_message_to_user.side_effect = InvalidTelegramUserIdError("bad id")
        resp = c.post("/api/telegram/send_message", json={
            "user_id": "bad", "message": "Hello",
        })
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_user_id"

    def test_send_telegram_api_error(self):
        c, svc = _make_app()
        svc.send_message_to_user.side_effect = TelegramAPIError("api fail")
        resp = c.post("/api/telegram/send_message", json={
            "user_id": "100", "message": "Hello",
        })
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "telegram_bad_request"

    def test_send_not_configured_error(self):
        c, svc = _make_app()
        svc.send_message_to_user.side_effect = TelegramNotConfiguredError("no token")
        resp = c.post("/api/telegram/send_message", json={
            "user_id": "100", "message": "Hello",
        })
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "telegram_not_configured"

    def test_send_unexpected_error(self):
        c, svc = _make_app()
        svc.send_message_to_user.side_effect = RuntimeError("boom")
        resp = c.post("/api/telegram/send_message", json={
            "user_id": "100", "message": "Hello",
        })
        assert resp.status_code == 500
        assert resp.json()["detail"]["code"] == "unexpected_error"


class TestBroadcast:
    def test_broadcast_success(self):
        c, svc = _make_app()
        svc.broadcast_message_to_all.return_value = {"sent": 5, "failed": 0}
        resp = c.post("/api/telegram/broadcast", json={
            "message": "Broadcast message",
        })
        assert resp.status_code == 200

    def test_broadcast_bot_not_configured(self):
        c, svc = _make_app(bot_configured=False)
        resp = c.post("/api/telegram/broadcast", json={"message": "Hi"})
        assert resp.status_code == 400


class TestDeleteSentMessage:
    def test_delete(self):
        c, svc = _make_app()
        resp = c.delete("/api/telegram/sent_messages/1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
