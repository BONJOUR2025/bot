"""Порядок сообщений hh — это контракт, а не деталь реализации.

Вызывающие берут «последний ответ кандидата» как `applicant[-1]`, а карточка
рисует переписку сверху вниз. Раньше `get_messages` делала `reversed(items)`
с комментарием «hh returns newest first»; на живом API это неверно — hh
отдаёт сначала исходный отклик. Из-за этого `applicant[-1]` возвращал самый
СТАРЫЙ ответ кандидата (пустой текст первичного отклика), и вебхук hh молча
выходил по `if not text`. Ни одно сообщение через вебхук не доехало: всё
вытягивал часовой опрос, который берёт max() по дате и потому уцелел.
"""
from __future__ import annotations

import httpx
import pytest

from app.services import hh_api
from tests.conftest import run_async

NEG = "5484058590"


def _msg(mid, created, who, text):
    return {
        "id": mid,
        "text": text,
        "created_at": created,
        "author": {"participant_type": who, "name": "Валерия"},
        "read": True,
    }


# Реальная выдача hh по отклику: первым идёт сам отклик с пустым текстом.
LIVE = [
    _msg("15024283810", "2026-08-07T09:05:46+0300", "applicant", ""),
    _msg("15057750407", "2026-08-10T21:10:24+0300", "employer", "Вы ещё в поиске работы?"),
    _msg("15060693049", "2026-08-11T09:00:38+0300", "applicant", "Добрый день, да"),
    _msg("15060949797", "2026-08-11T09:15:38+0300", "employer", "У вас есть гражданство РФ?"),
    _msg("15064328933", "2026-08-11T12:01:26+0300", "applicant", "Да"),
]


def _patch(monkeypatch, items, status=200):
    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None, params=None):
            return httpx.Response(status, json={"items": items},
                                  request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)


class TestChronologicalOrder:
    def test_oldest_first(self, monkeypatch):
        _patch(monkeypatch, LIVE)
        got = run_async(hh_api.get_messages("tok", NEG))
        assert [m["id"] for m in got] == [m["id"] for m in LIVE]

    def test_order_is_imposed_not_assumed(self, monkeypatch):
        """Если hh однажды начнёт отдавать newest-first, результат не изменится
        — именно эта невысказанная догадка и стоила нам вебхука."""
        _patch(monkeypatch, list(reversed(LIVE)))
        got = run_async(hh_api.get_messages("tok", NEG))
        assert [m["id"] for m in got] == [m["id"] for m in LIVE]

    def test_last_applicant_message_is_the_newest_reply(self, monkeypatch):
        """Ровно то выражение, которым пользуется вебхук hh."""
        _patch(monkeypatch, LIVE)
        got = run_async(hh_api.get_messages("tok", NEG))
        applicant = [m for m in got if m["author_type"] == "applicant"]

        assert applicant[-1]["text"] == "Да"
        assert applicant[-1]["id"] == "15064328933"

    def test_undated_message_never_becomes_the_latest(self, monkeypatch):
        """Битая дата не должна превращать запись в «свежий ответ»."""
        broken = _msg("999", "", "applicant", "мусор")
        _patch(monkeypatch, LIVE + [broken])
        got = run_async(hh_api.get_messages("tok", NEG))

        assert got[0]["id"] == "999"
        applicant = [m for m in got if m["author_type"] == "applicant"]
        assert applicant[-1]["text"] == "Да"


class TestDegradesQuietly:
    @pytest.mark.parametrize("status", [403, 404])
    def test_no_access_returns_empty(self, monkeypatch, status):
        _patch(monkeypatch, LIVE, status=status)
        assert run_async(hh_api.get_messages("tok", NEG)) == []
