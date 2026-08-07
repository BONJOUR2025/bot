"""Tests for hh.ru access-token auto-renewal in the recruitment sync.

Regression context: hh_api.refresh_access_token() existed but was never called
from anywhere, so the token silently expired every ~2 weeks and the whole hh
integration stopped pulling responses. Production was found with a token that
had expired a month earlier and a 403 on every sync.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services import recruitment_sync as sync
from tests.conftest import run_async


class _FakeSource:
    def __init__(self, *, refresh_token="rt-old", token_expires_at=None, access_token="at-old"):
        self.source = "hh"
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_expires_at = token_expires_at
        self.client_id = ""
        self.client_secret = ""
        self.last_error = "previous failure"


class _FakeDb:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


@pytest.fixture(autouse=True)
def reset_notify_guard():
    sync._hh_refresh_failure_notified = False
    yield
    sync._hh_refresh_failure_notified = False


@pytest.fixture
def no_notify(monkeypatch):
    sent = []

    async def fake_send(text):
        sent.append(text)
        return True

    monkeypatch.setattr("app.services.notify.send_notification", fake_send)
    return sent


def _patch_refresh(monkeypatch, result=None, exc=None):
    calls = []

    async def fake_refresh(client_id, client_secret, refresh_token):
        calls.append(refresh_token)
        if exc:
            raise exc
        return result

    monkeypatch.setattr("app.services.hh_api.refresh_access_token", fake_refresh)
    return calls


class TestSkipsWhenNotNeeded:
    def test_no_refresh_token_does_nothing(self, monkeypatch):
        calls = _patch_refresh(monkeypatch, result={})
        src = _FakeSource(refresh_token="")
        assert run_async(sync._refresh_hh_token_if_needed(_FakeDb(), src)) is None
        assert calls == []

    def test_token_valid_well_into_the_future_is_left_alone(self, monkeypatch):
        calls = _patch_refresh(monkeypatch, result={})
        src = _FakeSource(token_expires_at=datetime.utcnow() + timedelta(days=10))
        assert run_async(sync._refresh_hh_token_if_needed(_FakeDb(), src)) is None
        assert calls == []
        assert src.access_token == "at-old"


class TestRefreshes:
    def test_expired_token_is_refreshed_and_saved(self, monkeypatch):
        _patch_refresh(monkeypatch, result={
            "access_token": "at-new", "refresh_token": "rt-new", "expires_in": 1209599,
        })
        src = _FakeSource(token_expires_at=datetime.utcnow() - timedelta(days=30))
        db = _FakeDb()

        token = run_async(sync._refresh_hh_token_if_needed(db, src))

        assert token == "at-new"
        assert src.access_token == "at-new"
        assert src.token_expires_at > datetime.utcnow() + timedelta(days=13)
        assert src.last_error == ""
        assert db.commits == 1

    def test_rotated_refresh_token_is_stored(self, monkeypatch):
        """hh issues a new refresh_token on every use — keeping the old one
        would make the *next* refresh fail with an already-used token."""
        _patch_refresh(monkeypatch, result={
            "access_token": "at-new", "refresh_token": "rt-new", "expires_in": 100,
        })
        src = _FakeSource(token_expires_at=datetime.utcnow() - timedelta(days=1))

        run_async(sync._refresh_hh_token_if_needed(_FakeDb(), src))

        assert src.refresh_token == "rt-new"

    def test_token_near_expiry_is_refreshed_before_it_dies(self, monkeypatch):
        calls = _patch_refresh(monkeypatch, result={"access_token": "at-new", "expires_in": 100})
        # inside the 1-day margin
        src = _FakeSource(token_expires_at=datetime.utcnow() + timedelta(hours=2))

        run_async(sync._refresh_hh_token_if_needed(_FakeDb(), src))

        assert calls == ["rt-old"]

    def test_missing_expiry_triggers_a_refresh(self, monkeypatch):
        """Older rows predate token_expires_at being recorded — treat unknown
        as "refresh it" rather than assuming it is still good."""
        calls = _patch_refresh(monkeypatch, result={"access_token": "at-new", "expires_in": 100})
        src = _FakeSource(token_expires_at=None)

        run_async(sync._refresh_hh_token_if_needed(_FakeDb(), src))

        assert calls == ["rt-old"]

    def test_refresh_token_kept_when_response_omits_a_new_one(self, monkeypatch):
        _patch_refresh(monkeypatch, result={"access_token": "at-new", "expires_in": 100})
        src = _FakeSource(token_expires_at=datetime.utcnow() - timedelta(days=1))

        run_async(sync._refresh_hh_token_if_needed(_FakeDb(), src))

        assert src.refresh_token == "rt-old"


class TestFailure:
    def test_failure_returns_none_and_notifies_admin(self, monkeypatch, no_notify):
        _patch_refresh(monkeypatch, exc=ValueError("token revoked"))
        src = _FakeSource(token_expires_at=datetime.utcnow() - timedelta(days=1))

        result = run_async(sync._refresh_hh_token_if_needed(_FakeDb(), src))

        assert result is None
        assert src.access_token == "at-old"  # untouched
        assert "token revoked" in src.last_error
        assert len(no_notify) == 1
        assert "hh.ru" in no_notify[0]

    def test_repeated_failures_notify_only_once(self, monkeypatch, no_notify):
        _patch_refresh(monkeypatch, exc=ValueError("token revoked"))
        src = _FakeSource(token_expires_at=datetime.utcnow() - timedelta(days=1))

        for _ in range(3):
            run_async(sync._refresh_hh_token_if_needed(_FakeDb(), src))

        assert len(no_notify) == 1

    def test_guard_resets_after_a_successful_refresh(self, monkeypatch, no_notify):
        """A recovered source must be able to alert again if it breaks later."""
        _patch_refresh(monkeypatch, exc=ValueError("boom"))
        src = _FakeSource(token_expires_at=datetime.utcnow() - timedelta(days=1))
        run_async(sync._refresh_hh_token_if_needed(_FakeDb(), src))
        assert len(no_notify) == 1

        _patch_refresh(monkeypatch, result={"access_token": "at-new", "expires_in": 100})
        run_async(sync._refresh_hh_token_if_needed(_FakeDb(), src))

        src.token_expires_at = datetime.utcnow() - timedelta(days=1)
        _patch_refresh(monkeypatch, exc=ValueError("boom again"))
        run_async(sync._refresh_hh_token_if_needed(_FakeDb(), src))

        assert len(no_notify) == 2
