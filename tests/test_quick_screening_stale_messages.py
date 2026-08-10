"""Регрессия: старое сообщение из истории чата не должно засчитываться как
ответ на только что заданный вопрос.

Найдено в бою при первом запуске быстрого режима: `_check_avito_messages`
брал `max(incoming, key=created_at)` — последнее сообщение кандидата в чате
вообще, без сверки со временем вопроса. Переписка на Авито тянется с прошлых
откликов, поэтому 18 из 34 засчитанных «ответов» оказались старыми
сообщениями — самое старое от сентября 2024, где номер телефона
«89112876560» был записан как ответ на «У вас есть гражданство РФ?».

Последствие хуже, чем мусор в базе: кандидат молчит, а опрос считает вопрос
пройденным и отправляет следующий.

Второй найденный в бою случай (1fc3f0b → фикс в этом же файле): avito_api.get_messages
стал отдавать created_at ISO-строкой вместо сырого unix-времени (чтобы
починить отображение дат в чате), а фильтр ниже сравнивал (created_at or 0) >
asked_ts напрямую — то есть строку с float. TypeError ловился в try/except
на каждое сообщение молча, и ни один ответ кандидата в Авито не долетал до
опроса, пока это не всплыло как «зависание» после массового запуска опроса.
Фикстуры здесь поэтому строят created_at как ISO-строку (реальная форма
avito_api.get_messages), а _filter буквально использует _iso_to_ts из
recruitment_sync, а не копию логики — расхождение между тестом и кодом было
как раз тем, что позволило регрессии проскочить незамеченной.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.recruitment_sync import _asked_at_ts, _iso_to_ts


ASKED = datetime(2026, 8, 10, 9, 54, 0)


def _ts(dt: datetime) -> float:
    return dt.replace(tzinfo=timezone.utc).timestamp()


def _iso(dt: datetime) -> str:
    """Naive-UTC ISO string — ровно то, что avito_api.get_messages кладёт в
    created_at (через datetime.utcfromtimestamp(...).isoformat())."""
    return dt.isoformat()


def _filter(messages, state):
    """Та же отсечка, что в _check_avito_messages — использует реальный
    _iso_to_ts, а не отдельную копию парсинга."""
    asked_ts = _asked_at_ts(state)
    if asked_ts is None:
        return messages
    return [m for m in messages if (_iso_to_ts(m.get("created_at")) or 0) > asked_ts]


class TestAskedAtTimestamp:
    def test_parses_naive_utc_isoformat(self):
        assert _asked_at_ts({"asked_at": ASKED.isoformat()}) == _ts(ASKED)

    def test_missing_or_broken_returns_none(self):
        assert _asked_at_ts({}) is None
        assert _asked_at_ts({"asked_at": ""}) is None
        assert _asked_at_ts({"asked_at": "не дата"}) is None
        assert _asked_at_ts(None) is None


class TestMessageCreatedAtIsAnIsoString:
    """avito_api.get_messages returns created_at as an ISO string (see its
    own tests in test_avito_job_chats.py::TestGetMessages) — a raw number
    here would break every comparison below with a silent TypeError."""

    def test_iso_to_ts_parses_the_real_shape(self):
        assert _iso_to_ts(_iso(ASKED)) == _ts(ASKED)

    def test_iso_to_ts_rejects_a_raw_number_gracefully(self):
        """If something upstream ever regresses back to a raw epoch number,
        this must return None (→ filtered out as "no timestamp"), not raise —
        the old bug was a silent TypeError deep inside a list comprehension."""
        assert _iso_to_ts(1786356003) is None  # type: ignore[arg-type]


class TestStaleMessageFiltering:
    def test_old_message_is_not_counted_as_an_answer(self):
        """Ровно тот случай из боя: телефон, написанный почти два года назад."""
        messages = [{"id": "1", "text": "89112876560", "created_at": _iso(datetime(2024, 9, 9, 11, 23))}]
        assert _filter(messages, {"asked_at": ASKED.isoformat()}) == []

    def test_reply_after_the_question_is_kept(self):
        fresh = {"id": "2", "text": "Есть", "created_at": _iso(ASKED + timedelta(minutes=3))}
        assert _filter([fresh], {"asked_at": ASKED.isoformat()}) == [fresh]

    def test_mixed_history_keeps_only_the_fresh_reply(self):
        old1 = {"id": "1", "text": "Актуально?", "created_at": _iso(datetime(2026, 6, 18, 15, 7))}
        old2 = {"id": "2", "text": "Уже нет(", "created_at": _iso(datetime(2026, 1, 27, 17, 49))}
        fresh = {"id": "3", "text": "Да, гражданство есть", "created_at": _iso(ASKED + timedelta(minutes=1))}

        kept = _filter([old1, old2, fresh], {"asked_at": ASKED.isoformat()})

        assert kept == [fresh]
        # И именно свежее становится «последним» — раньше max() выбирал old1.
        assert max(kept, key=lambda m: _iso_to_ts(m["created_at"]))["text"] == "Да, гражданство есть"

    def test_message_exactly_at_ask_time_is_excluded(self):
        """Строго больше: сообщение, отправленное в ту же секунду, что и наш
        вопрос, физически не может быть ответом на него."""
        same = {"id": "1", "text": "?", "created_at": _iso(ASKED)}
        assert _filter([same], {"asked_at": ASKED.isoformat()}) == []

    def test_without_asked_at_nothing_is_filtered(self):
        """Состояния, записанные до появления отсечки, не должны внезапно
        перестать обрабатываться — лучше прежнее поведение, чем полное
        игнорирование входящих."""
        old = {"id": "1", "text": "старое", "created_at": _iso(datetime(2025, 1, 1))}
        assert _filter([old], {}) == [old]
