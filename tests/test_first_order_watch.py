"""Поздравление с первым заказом на новой точке.

Заведено под «Чистомат», которого в Agbis ещё нет. Отсюда устройство:
подразделение ищется по НАЗВАНИЮ, а не по номеру — номер появится только
вместе с точкой, а сторож должен сработать сам в день её открытия.

Свойство, ради которого написаны тесты: **сработать ровно один раз**.
Первый заказ бывает один, и повторное поздравление обесценило бы его.
"""
from __future__ import annotations

import pytest

from app.services import first_order_watch as fw
from tests.conftest import run_async


ORDER = {"doc_num": "64863-5", "doc_date": None, "dep_id": 25, "dep_name": "Чистомат"}


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def fake(text):
        out.append(text)
        return True

    monkeypatch.setattr("app.services.notify.send_notification", fake)
    return out


@pytest.fixture
def cfg(monkeypatch):
    """Конфиг в памяти, чтобы тест не трогал боевой config.json."""
    store = {}

    class _Svc:
        def load(self):
            return dict(store)

        def patch(self, data):
            store.update(data)

    monkeypatch.setattr("app.services.config_service.ConfigService", lambda: _Svc())
    return store


class TestFiresOnce:
    def test_first_order_triggers_celebration(self, sent, cfg, monkeypatch):
        monkeypatch.setattr(fw, "find_first_order", lambda part: ORDER)
        assert run_async(fw.check_and_notify()) is True

        assert len(sent) == 1
        assert "ПЕРВЫЙ ЗАКАЗ" in sent[0]
        assert "ЧИСТОМАТ" in sent[0]
        assert "64863-5" in sent[0]

    def test_second_check_stays_silent(self, sent, cfg, monkeypatch):
        monkeypatch.setattr(fw, "find_first_order", lambda part: ORDER)
        run_async(fw.check_and_notify())
        run_async(fw.check_and_notify())
        run_async(fw.check_and_notify())

        assert len(sent) == 1, "поздравлять с первым заказом можно только один раз"

    def test_marked_before_sending(self, cfg, monkeypatch):
        """Пометка ставится ДО отправки: недоступный Telegram должен стоить
        одного пропущенного поздравления, а не поздравления каждые 15 минут."""
        monkeypatch.setattr(fw, "find_first_order", lambda part: ORDER)

        async def boom(text):
            raise RuntimeError("telegram down")

        monkeypatch.setattr("app.services.notify.send_notification", boom)
        with pytest.raises(RuntimeError):
            run_async(fw.check_and_notify())

        assert cfg[fw.CFG_SEEN]["чистомат"] == "64863-5"


class TestQuietUntilItHappens:
    def test_no_such_department_yet(self, sent, cfg, monkeypatch):
        """Пока точки нет — это норма, а не ошибка."""
        monkeypatch.setattr(fw, "find_first_order", lambda part: None)
        assert run_async(fw.check_and_notify()) is False
        assert sent == []

    def test_firebird_failure_is_not_fatal(self, sent, cfg, monkeypatch):
        def boom(part):
            raise RuntimeError("Firebird недоступен")

        monkeypatch.setattr(fw, "find_first_order", boom)
        assert run_async(fw.check_and_notify()) is False
        assert sent == []
        assert not cfg.get(fw.CFG_SEEN), "сбой не должен помечать точку как отработанную"


class TestMessage:
    def test_it_is_actually_joyful(self):
        text = fw._celebration(ORDER)
        assert text.count("🎉") >= 3
        assert "Поздравляю" in text

    def test_department_name_comes_from_agbis(self):
        """Название берётся из базы, а не зашито: точку могут назвать
        «ЧистоМат №1» или «Чистомат Озерки»."""
        text = fw._celebration({**ORDER, "dep_name": "ЧистоМат №1"})
        assert "ЧИСТОМАТ №1" in text

    def test_date_without_time_is_shown_as_a_date(self):
        """docs.doc_date хранит только дату — «в 00:00» было бы враньём."""
        from datetime import date, datetime
        assert "00:00" not in fw._celebration({**ORDER, "doc_date": date(2026, 8, 14)})
        assert "14.08.2026" in fw._celebration({**ORDER, "doc_date": date(2026, 8, 14)})
        with_time = fw._celebration({**ORDER, "doc_date": datetime(2026, 8, 14, 15, 30)})
        assert "15:30" in with_time
