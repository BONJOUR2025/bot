"""Comprehensive tests for API message and template endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.messages import create_message_router
from app.api.dependencies import get_current_user
from app.schemas.message import MessageOut
from app.services.access_control_service import ResolvedUser


def _resolved():
    return ResolvedUser(
        id="admin", login="admin", role_id="owner", role_name="Owner",
        permissions=["*"], bot_buttons=["*"], display_name="Admin",
        allowed_employee_ids=None, allowed_departments=None,
    )


def _msg_out(**kw):
    defaults = dict(
        id="1", user_id="100", name="Иван",
        text="Тестовое сообщение", photo=None,
        status="Отправлено", accepted=False,
        timestamp="2025-01-15T10:30:00", message_id=12345,
    )
    defaults.update(kw)
    return MessageOut(**defaults)


def _make_app():
    msg_svc = AsyncMock()
    tpl_svc = AsyncMock()

    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: _resolved()
    router = create_message_router(msg_svc, tpl_svc)
    app.include_router(router, prefix="/api")
    return app, msg_svc, tpl_svc


class TestListMessages:
    def test_list(self):
        app, msvc, tsvc = _make_app()
        msvc.list_messages.return_value = [_msg_out()]
        c = TestClient(app)
        resp = c.get("/api/messages/")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_empty(self):
        app, msvc, tsvc = _make_app()
        msvc.list_messages.return_value = []
        c = TestClient(app)
        resp = c.get("/api/messages/")
        assert resp.json() == []


class TestSendMessage:
    def test_send(self):
        app, msvc, tsvc = _make_app()
        msvc.send_message.return_value = _msg_out()
        c = TestClient(app)
        resp = c.post("/api/messages/", data={
            "user_id": "100",
            "message": "Hello",
        })
        assert resp.status_code == 200
        msvc.send_message.assert_called_once()


class TestAcceptMessage:
    def test_accept(self):
        app, msvc, tsvc = _make_app()
        msvc.accept_message.return_value = _msg_out(accepted=True)
        c = TestClient(app)
        resp = c.post("/api/messages/1/accept")
        assert resp.status_code == 200

    def test_accept_not_found(self):
        app, msvc, tsvc = _make_app()
        msvc.accept_message.return_value = None
        c = TestClient(app)
        resp = c.post("/api/messages/999/accept")
        assert resp.status_code == 404


class TestTemplates:
    def test_list_templates(self):
        app, msvc, tsvc = _make_app()
        tsvc.list_templates.return_value = [{"id": "1", "name": "T1", "text": "Body"}]
        c = TestClient(app)
        resp = c.get("/api/messages/templates")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_create_template(self):
        app, msvc, tsvc = _make_app()
        tsvc.create_template.return_value = {"id": "2", "name": "New", "text": "New body"}
        c = TestClient(app)
        resp = c.post("/api/messages/templates", data={"name": "New", "text": "New body"})
        assert resp.status_code == 200

    def test_delete_template(self):
        app, msvc, tsvc = _make_app()
        c = TestClient(app)
        resp = c.delete("/api/messages/templates/1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
