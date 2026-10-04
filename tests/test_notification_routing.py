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


# ── получатель по @username ────────────────────────────────────────────
class _BotUsers:
    def __init__(self, users):
        self.users = users

    def list(self):
        return self.users


@pytest.fixture
def bot_users(monkeypatch):
    users = [{"telegram_id": "555", "username": "Ar_Oganov"}]
    monkeypatch.setattr("app.data.bot_user_repository.get_bot_user_repository", lambda: _BotUsers(users))
    return users


def test_username_normalized():
    assert nr.normalize_username("@Ar_Oganov") == "@ar_oganov"
    assert nr.normalize_username("Ar_Oganov") == "@ar_oganov"
    assert nr.normalize_username("@ab") is None          # короче 5 символов не бывает
    assert nr.normalize_username("@1abc_def") is None    # не может начинаться с цифры
    assert nr.normalize_username("12345") is None


def test_username_resolved_case_insensitively(bot_users):
    assert nr.resolve_username("@ar_OGANOV") == 555
    assert nr.resolve_username("@nobody_here") is None


def test_pending_username_skipped_until_user_starts_bot(routing, bot_users):
    routing({"payouts": {"enabled": True, "recipients": [7, "@new_admin", "@Ar_Oganov"]}})
    assert nr.recipients("payouts") == [7, 555]
    # Человек нажал «Старт» — бот записал его, и уведомления пошли.
    bot_users.append({"telegram_id": "777", "username": "new_admin"})
    assert nr.recipients("payouts") == [7, 777, 555]  # порядок — как в настройках


def test_api_saves_id_for_known_username_and_keeps_pending(routing, bot_users, tmp_path):
    from app.api.notification_routing import GroupIn, RoutingIn, create_notification_routing_router

    router = create_notification_routing_router()
    put = next(r.endpoint for r in router.routes if "PUT" in r.methods)
    asyncio.run(put(RoutingIn(groups={"payouts": GroupIn(recipients=[7, "@AR_OGANOV", "@new_admin", "555"])})))
    saved = json.loads((tmp_path / "routing.json").read_text(encoding="utf-8"))
    assert saved["groups"]["payouts"]["recipients"] == [7, 555, "@new_admin"]


def test_api_rejects_garbage_username(routing, bot_users):
    from fastapi import HTTPException

    from app.api.notification_routing import GroupIn, RoutingIn, create_notification_routing_router

    put = next(r.endpoint for r in create_notification_routing_router().routes if "PUT" in r.methods)
    with pytest.raises(HTTPException):
        asyncio.run(put(RoutingIn(groups={"payouts": GroupIn(recipients=["@ab"])})))
