"""Группы уведомлений: умолчание, выключение, несколько получателей."""
import asyncio
import json

import pytest

from app.services import notification_routing as nr
from app.services import notify


@pytest.fixture
def routing(tmp_path, monkeypatch):
    path = tmp_path / "routing.json"
    monkeypatch.setattr(nr, "_path", lambda: str(path))
    monkeypatch.setattr(nr, "default_recipient", lambda: 100)

    def write(groups):
        path.write_text(json.dumps({"groups": groups}), encoding="utf-8")
    return write


def test_unconfigured_group_goes_to_default(routing):
    assert nr.recipients("payouts") == [100]
    assert nr.group_settings("payouts")["configured"] is False


def test_unknown_group_falls_back_to_system(routing):
    routing({"system": {"enabled": True, "recipients": [7]}})
    assert nr.recipients("nonexistent") == [7]


def test_disabled_group_sends_nowhere(routing):
    routing({"payouts": {"enabled": False, "recipients": [5]}})
    assert nr.recipients("payouts") == []


def test_configured_recipients_deduplicated(routing):
    routing({"candidate_messages": {"enabled": True, "recipients": [5, 6, 5]}})
    assert nr.recipients("candidate_messages") == [5, 6]
    assert nr.recipients("payouts") == [100]


def test_broken_file_keeps_default(routing, tmp_path):
    (tmp_path / "routing.json").write_text("{не json", encoding="utf-8")
    assert nr.recipients("digest") == [100]


def test_send_notification_reaches_every_recipient(routing, monkeypatch):
    routing({"workshop": {"enabled": True, "recipients": [11, 22]}})
    sent = []

    class _Resp:
        status_code = 200
        text = ""

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json):
            sent.append(json)
            return _Resp()

    monkeypatch.setattr(notify.httpx, "AsyncClient", _Client)
    monkeypatch.setattr("app.config.TOKEN", "t", raising=False)
    ok = asyncio.run(notify.notify_group("workshop", "привет", buttons=[[{"text": "ok", "callback_data": "x"}]]))
    assert ok is True
    assert [m["chat_id"] for m in sent] == [11, 22]
    assert all(m["reply_markup"]["inline_keyboard"] for m in sent)


def test_disabled_group_sends_nothing(routing, monkeypatch):
    routing({"digest": {"enabled": False, "recipients": [11]}})
    monkeypatch.setattr(notify.httpx, "AsyncClient", lambda **kw: pytest.fail("не должно отправляться"))
    assert asyncio.run(notify.notify_group("digest", "сводка")) is False
