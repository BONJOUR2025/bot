"""Tests for deriving Avito job applicants from Messenger chats.

Avito paywalls the whole job/* API behind the "Максимальная" Работа
subscription — verified against the live account, where even an endpoint that
needs no scope answers 402 — while the Messenger API stays open. Each chat
carries the listing it belongs to, so filtering chats by the vacancy's item id
yields its applicants.
"""
from __future__ import annotations

import httpx
import pytest

from app.services import avito_api
from tests.conftest import run_async

OUR_ID = "21315059"
VACANCY_ITEM = "2353269952"


def _chat(chat_id, item_id=VACANCY_ITEM, name="Станислав", created=1786083483):
    return {
        "id": chat_id,
        "created": created,
        "updated": created + 100,
        "context": {"type": "item", "value": {"id": int(item_id), "title": "Мастер по ремонту обуви"}},
        "users": [
            {"id": int(OUR_ID), "name": "Мастерская Bonjour"},
            {"id": 11052017, "name": name},
        ],
    }


def _patch_pages(monkeypatch, pages, capture=None):
    """pages: list of chat-lists, returned in order for successive offsets."""
    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None, params=None):
            if capture is not None:
                capture.append(dict(params or {}))
            idx = (params or {}).get("offset", 0) // (params or {}).get("limit", 100)
            chats = pages[idx] if idx < len(pages) else []
            return httpx.Response(200, json={"chats": chats}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)


class TestFiltering:
    def test_only_chats_for_the_given_vacancy_are_returned(self, monkeypatch):
        _patch_pages(monkeypatch, [[
            _chat("chat-1"),
            _chat("chat-2", item_id="9999999", name="Покупатель дивана"),
            _chat("chat-3", name="Дмитрий"),
        ]])
        result = run_async(avito_api.get_job_chats("tok", OUR_ID, VACANCY_ITEM))

        assert [r["external_id"] for r in result] == ["chat-1", "chat-3"]

    def test_counterparty_name_is_used_not_our_own(self, monkeypatch):
        _patch_pages(monkeypatch, [[_chat("chat-1", name="Ангелина Нестеренко")]])
        result = run_async(avito_api.get_job_chats("tok", OUR_ID, VACANCY_ITEM))

        assert result[0]["name"] == "Ангелина Нестеренко"

    def test_chat_id_is_both_the_external_key_and_the_reply_address(self, monkeypatch):
        """There is no application id on this path, so the chat id has to
        serve as the stable key as well as the address to write to."""
        _patch_pages(monkeypatch, [[_chat("u2i-abc")]])
        result = run_async(avito_api.get_job_chats("tok", OUR_ID, VACANCY_ITEM))

        assert result[0]["external_id"] == "u2i-abc"
        assert result[0]["platform_chat_id"] == "u2i-abc"

    def test_created_timestamp_becomes_applied_at(self, monkeypatch):
        _patch_pages(monkeypatch, [[_chat("chat-1", created=1786083483)]])
        result = run_async(avito_api.get_job_chats("tok", OUR_ID, VACANCY_ITEM))

        assert result[0]["applied_at"].startswith("2026-")

    def test_missing_counterparty_falls_back_to_a_placeholder(self, monkeypatch):
        chat = _chat("chat-1")
        chat["users"] = [{"id": int(OUR_ID), "name": "Мастерская Bonjour"}]
        _patch_pages(monkeypatch, [[chat]])
        result = run_async(avito_api.get_job_chats("tok", OUR_ID, VACANCY_ITEM))

        assert result[0]["name"] == "Кандидат"

    def test_chat_without_item_context_is_skipped(self, monkeypatch):
        chat = _chat("chat-1")
        chat["context"] = {}
        _patch_pages(monkeypatch, [[chat]])
        assert run_async(avito_api.get_job_chats("tok", OUR_ID, VACANCY_ITEM)) == []


class TestPagination:
    def test_walks_pages_until_a_short_one(self, monkeypatch):
        params = []
        _patch_pages(monkeypatch, [
            [_chat(f"c{i}") for i in range(100)],
            [_chat("c100"), _chat("c101")],
        ], capture=params)
        result = run_async(avito_api.get_job_chats("tok", OUR_ID, VACANCY_ITEM))

        assert len(result) == 102
        assert [p["offset"] for p in params] == [0, 100]

    def test_stops_at_max_pages(self, monkeypatch):
        """A full-page result forever must not loop indefinitely."""
        _patch_pages(monkeypatch, [[_chat(f"p{p}-{i}") for i in range(100)] for p in range(50)])
        result = run_async(avito_api.get_job_chats("tok", OUR_ID, VACANCY_ITEM, max_pages=3))

        assert len(result) == 300

    def test_empty_first_page_returns_nothing(self, monkeypatch):
        _patch_pages(monkeypatch, [[]])
        assert run_async(avito_api.get_job_chats("tok", OUR_ID, VACANCY_ITEM)) == []


class TestErrors:
    def test_403_explains_the_likely_cause(self, monkeypatch):
        class _FakeClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, headers=None, params=None):
                return httpx.Response(403, json={"error": "forbidden"},
                                       request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
        with pytest.raises(ValueError, match="messenger:read"):
            run_async(avito_api.get_job_chats("tok", OUR_ID, VACANCY_ITEM))


class TestApplicationsPaywall:
    def test_402_raises_a_message_naming_the_subscription(self, monkeypatch):
        """The sync's fallback keys off this wording, so it is load-bearing."""
        class _FakeClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, headers=None, params=None):
                return httpx.Response(
                    402,
                    json={"code": 402, "message": "Перейдите на Максимальную подписку"},
                    request=httpx.Request("GET", url),
                )

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
        with pytest.raises(ValueError, match="Максимальной подписки"):
            run_async(avito_api.get_applications_for_vacancy("tok", OUR_ID, VACANCY_ITEM))


class TestGetMessages:
    """Avito's messenger API reports `created` as Unix epoch *seconds*
    (verified against the live account), but the frontend's fmtMsgTime does
    `new Date(created_at)`, which treats a bare number as milliseconds — so
    every message rendered as 21.01.1970 until this converted it to an ISO
    string, the same shape hh_api.get_messages already returns."""

    def _patch_messages(self, monkeypatch, items):
        class _FakeClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, headers=None, params=None):
                return httpx.Response(200, json=items, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    def _message(self, msg_id="m1", text="Есть ли опыт?", direction="out", created=1786356003):
        return {
            "id": msg_id,
            "type": "text",
            "direction": direction,
            "created": created,
            "content": {"text": text},
        }

    def test_created_at_is_an_iso_string_not_a_raw_epoch(self, monkeypatch):
        self._patch_messages(monkeypatch, [self._message(created=1786356003)])
        result = run_async(avito_api.get_messages("tok", OUR_ID, "chat-1"))

        assert result[0]["created_at"] == "2026-08-10T10:00:03"

    def test_direction_maps_to_author_type(self, monkeypatch):
        # Фикстура в «сыром» порядке Авито — новые сверху.
        self._patch_messages(monkeypatch, [
            self._message(msg_id="m1", direction="in", text="Здравствуйте"),
            self._message(msg_id="m2", direction="out", text="Добрый день"),
        ])
        result = run_async(avito_api.get_messages("tok", OUR_ID, "chat-1"))

        assert {r["id"]: r["author_type"] for r in result} == {"m1": "applicant", "m2": "employer"}

    def test_messages_come_back_oldest_first(self, monkeypatch):
        """Авито отдаёт новые сверху, hh_api.get_messages — наоборот, и чат
        рисуется сверху вниз как любой мессенджер. Нормализуем к хронологии,
        иначе переписка в карточке читается задом наперёд."""
        self._patch_messages(monkeypatch, [
            self._message(msg_id="newest", created=1786356003),
            self._message(msg_id="middle", created=1786356002),
            self._message(msg_id="oldest", created=1786356001),
        ])
        result = run_async(avito_api.get_messages("tok", OUR_ID, "chat-1"))

        assert [r["id"] for r in result] == ["oldest", "middle", "newest"]

    def test_non_text_messages_are_skipped(self, monkeypatch):
        image = {"id": "m0", "type": "image", "direction": "in", "created": 1786356003}
        self._patch_messages(monkeypatch, [image, self._message(msg_id="m1")])
        result = run_async(avito_api.get_messages("tok", OUR_ID, "chat-1"))

        assert [r["id"] for r in result] == ["m1"]
