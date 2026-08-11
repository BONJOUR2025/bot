"""Tests for the Agbis full-size photo client.

Firebird and the storage agent are both stubbed. What matters here is the
behaviour that protects two things we don't own: the salon computer that
serves the files, and the service account whose session id must never leak.
"""
from __future__ import annotations

import os

import pytest

from app.services import agbis_photos as ap

JPEG = b"\xff\xd8\xff\xe0" + b"payload" * 40
PNG = b"\x89PNG\r\n\x1a\n" + b"payload" * 40


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Own cache directory and a clean session/agent state per test."""
    monkeypatch.setattr(ap.settings, "agbis_photo_cache_dir", str(tmp_path / "cache"))
    monkeypatch.setattr(ap.settings, "agbis_photo_cache_limit_mb", 1)
    monkeypatch.setattr(ap.settings, "agbis_storage_user", "bot")
    monkeypatch.setattr(ap.settings, "agbis_storage_password_sha1", "deadbeef")
    monkeypatch.setattr(ap, "_session", None)
    monkeypatch.setattr(ap, "_agent_cache", None)
    yield


AGENT = ap.StorageAgent(agent_id=1081, host="im-gate.com", port=10460)


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setattr(ap, "resolve_agent", lambda force=False: AGENT)
    return AGENT


# _download отдаёт (HTTP-код, байты), а не объект ответа: транспортом
# служит curl.exe, а не httpx — шлюз Agbis не отвечает на рукопожатие
# OpenSSL (см. _curl_get в сервисе).
def _resp(status=200, body=b""):
    return status, body


class TestAgent:
    def test_base_url_is_gateway_plus_port(self):
        assert AGENT.base_url == "https://im-gate.com/10460"

    def test_agent_is_cached_between_calls(self, monkeypatch):
        calls = []

        def fake_connect():
            calls.append(1)
            raise RuntimeError("должно вызваться только один раз")

        monkeypatch.setattr(ap, "_agent_cache", (AGENT, 9_999_999_999))
        monkeypatch.setattr("app.services.firebird_service._connect", fake_connect)
        assert ap.resolve_agent() is AGENT
        assert calls == []


class TestSessionId:
    """The agent's reply format isn't documented anywhere we control, so the
    session id is matched by shape rather than by key."""

    def test_extracts_from_bare_text(self):
        guid = "3C69D00E-978F-4610-A2A6-EDFC5D858820"
        assert ap._extract_session_id(guid) == guid

    def test_extracts_from_json(self):
        guid = "0256C67D-8E36-4D85-AE6E-CBE4BD39C56B"
        assert ap._extract_session_id('{"SessionID":"%s","ok":1}' % guid) == guid

    def test_none_when_absent(self):
        assert ap._extract_session_id("Access denied") is None
        assert ap._extract_session_id("") is None


class TestCache:
    def test_roundtrip(self):
        ap.cache_put("ABC123", JPEG)
        assert ap.cache_get("ABC123") == JPEG

    def test_key_is_case_insensitive(self):
        ap.cache_put("abc123", JPEG)
        assert ap.cache_get("ABC123") == JPEG

    def test_miss_returns_none(self):
        assert ap.cache_get("NOPE") is None

    def test_partial_files_are_not_served(self):
        ap.cache_put("ABC123", JPEG)
        open(os.path.join(ap._cache_dir(), "HALF.part"), "wb").write(b"x")
        assert ap.cache_get("HALF") is None

    def test_limit_evicts_least_recently_used(self, monkeypatch):
        """Cache is capped at 1 MB by the fixture; write past it and the
        oldest-accessed file must go, not the newest."""
        big = b"\xff\xd8\xff\xe0" + b"x" * (300 * 1024)
        for name in ("AAA", "BBB", "CCC", "DDD"):
            ap.cache_put(name, big)
        remaining = set(os.listdir(ap._cache_dir()))
        assert "DDD" in remaining, "последний записанный не должен вытесняться"
        assert len(remaining) < 4, "лимит не сработал"

    def test_stats_report_size_and_limit(self):
        ap.cache_put("ABC123", JPEG)
        stats = ap.cache_stats()
        assert stats["files"] == 1
        assert stats["bytes"] == len(JPEG)
        assert stats["limit_bytes"] == 1024 * 1024


class TestGetPhoto:
    def test_served_from_cache_without_touching_the_agent(self, agent, monkeypatch):
        ap.cache_put("MD5A", JPEG)

        def boom(*a, **k):
            pytest.fail("агент не должен вызываться при попадании в кэш")

        monkeypatch.setattr(ap, "_download", boom)
        monkeypatch.setattr(ap, "_get_session", boom)
        assert ap.get_photo("MD5A") == JPEG

    def test_downloads_and_caches(self, agent, monkeypatch):
        monkeypatch.setattr(ap, "_get_session", lambda a, force_new=False: "S1")
        monkeypatch.setattr(ap, "_download", lambda a, s, md5: _resp(200, JPEG))
        assert ap.get_photo("MD5B") == JPEG
        # Второй раз — уже из кэша, агент не нужен.
        monkeypatch.setattr(ap, "_download", lambda *a: pytest.fail("повторная загрузка"))
        assert ap.get_photo("MD5B") == JPEG

    def test_accepts_png(self, agent, monkeypatch):
        monkeypatch.setattr(ap, "_get_session", lambda a, force_new=False: "S1")
        monkeypatch.setattr(ap, "_download", lambda a, s, md5: _resp(200, PNG))
        assert ap.get_photo("MD5PNG") == PNG

    def test_stale_session_triggers_one_relogin(self, agent, monkeypatch):
        """A dead session comes back as an error page with HTTP 200, not as
        a 401 — so the retry is driven by the content, not the status."""
        sessions = []

        def get_session(a, force_new=False):
            sessions.append(force_new)
            return "S2" if force_new else "S1"

        def download(a, session, md5):
            return _resp(200, JPEG) if session == "S2" else _resp(200, b"<html>no session</html>")

        monkeypatch.setattr(ap, "_get_session", get_session)
        monkeypatch.setattr(ap, "_download", download)
        assert ap.get_photo("MD5C") == JPEG
        assert sessions == [False, True], "должен быть ровно один повторный логин"

    def test_gives_up_after_the_retry(self, agent, monkeypatch):
        monkeypatch.setattr(ap, "_get_session", lambda a, force_new=False: "S")
        monkeypatch.setattr(ap, "_download", lambda a, s, md5: _resp(200, b"nope"))
        with pytest.raises(ap.PhotoStorageError):
            ap.get_photo("MD5D")

    def test_failed_download_is_not_cached(self, agent, monkeypatch):
        monkeypatch.setattr(ap, "_get_session", lambda a, force_new=False: "S")
        monkeypatch.setattr(ap, "_download", lambda a, s, md5: _resp(500, b""))
        with pytest.raises(ap.PhotoStorageError):
            ap.get_photo("MD5E")
        assert ap.cache_get("MD5E") is None

    def test_unreachable_agent_raises_storage_error(self, agent, monkeypatch):
        monkeypatch.setattr(ap, "_get_session", lambda a, force_new=False: "S")

        def refused(*a, **k):
            raise OSError("connection refused")

        monkeypatch.setattr(ap, "_download", refused)
        with pytest.raises(ap.PhotoStorageError) as exc:
            ap.get_photo("MD5F")
        # Текст уходит прямо в интерфейс, поэтому проверяем, что он объясняет
        # оператору, что проверять, а не пересказывает исключение.
        assert "не отвечает" in str(exc.value)
        assert "connection refused" not in str(exc.value)
        ap._clear_outage()

    def test_empty_md5_rejected(self, agent):
        with pytest.raises(ap.PhotoStorageError):
            ap.get_photo("")


class TestCredentials:
    def test_missing_credentials_are_reported_clearly(self, agent, monkeypatch):
        monkeypatch.setattr(ap.settings, "agbis_storage_user", "")
        with pytest.raises(ap.PhotoStorageError) as exc:
            ap._login(agent)
        assert "AGBIS_STORAGE_USER" in str(exc.value)

    def test_login_sends_hash_not_plaintext(self, agent, monkeypatch):
        captured = {}

        # Транспорт — curl.exe, а не httpx: шлюз Agbis не отвечает на
        # рукопожатие OpenSSL (см. _curl_get).
        def fake_curl(url, params):
            captured["url"] = url
            captured["params"] = params
            return 200, b"3C69D00E-978F-4610-A2A6-EDFC5D858820"

        monkeypatch.setattr(ap, "_curl_get", fake_curl)
        session = ap._login(agent)
        assert session == "3C69D00E-978F-4610-A2A6-EDFC5D858820"
        assert captured["url"] == "https://im-gate.com/10460/Login"
        assert captured["params"]["Password"] == "deadbeef"
        assert captured["params"]["AsUser"] == 1
