"""Поздравление с первым заказом, сданным в «Чистомат».

Три факта из разбора боевой базы, которые определили устройство и которые
эти тесты защищают:

* Чистомат — это СКЛАД (`SCLADS.id=10125`, «Чистомат 1»), а не
  подразделение.
* Заказ считается сданным туда по `sclad_kredit_id` — складу приёмки. У
  заказа 1232305 `current_sclad_id=10125`, но принят он на Бестужевской, и
  считать его сданным в чистомат неверно.
* На складе уже лежат 19 заказов от 3-22 июня (номера 00003-00019, плотно
  за четыре дня, потом два месяца тишины) — тестовые. Поэтому «первый
  заказ» отсчитывается от установки сторожа, а не от начала времён.
"""
from __future__ import annotations

import pytest

from app.services import first_order_watch as fw
from tests.conftest import run_async


ORDER = {"doc_num": "00020", "doc_date": None, "sclad_name": "Чистомат 1", "doc_id": 5001}


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


@pytest.fixture
def db(monkeypatch):
    """Управляет тем, что «есть в базе»: последний заказ и следующий за ним."""
    state = {"latest": 5000, "next": None}
    monkeypatch.setattr(fw, "latest_doc_id", lambda part: state["latest"])
    monkeypatch.setattr(fw, "find_order_after", lambda part, after: state["next"])
    return state


class TestBaseline:
    def test_first_run_only_remembers_and_stays_silent(self, sent, cfg, db):
        """Июньские тестовые заказы не повод поздравлять: первый запуск
        просто запоминает, что уже есть."""
        db["next"] = ORDER  # даже если что-то найдётся — молчим
        assert run_async(fw.check_and_notify()) is False
        assert sent == []
        assert cfg[fw.CFG_BASELINE]["чистомат"] == 5000

    def test_celebrates_only_what_came_after(self, sent, cfg, db):
        run_async(fw.check_and_notify())      # запомнили точку отсчёта
        db["next"] = ORDER                     # приехал новый заказ
        assert run_async(fw.check_and_notify()) is True

        assert len(sent) == 1
        assert "ПЕРВЫЙ ЗАКАЗ" in sent[0]
        assert "ЧИСТОМАТ 1" in sent[0]
        assert "00020" in sent[0]

    def test_no_new_orders_means_silence(self, sent, cfg, db):
        run_async(fw.check_and_notify())
        db["next"] = None
        assert run_async(fw.check_and_notify()) is False
        assert sent == []

    def test_missing_sclad_does_not_set_a_baseline(self, sent, cfg, monkeypatch):
        """Склада ещё нет — ждём его появления, а не записываем ноль."""
        monkeypatch.setattr(fw, "latest_doc_id", lambda part: None)
        assert run_async(fw.check_and_notify()) is False
        assert not cfg.get(fw.CFG_BASELINE)


class TestFiresOnce:
    def test_second_check_stays_silent(self, sent, cfg, db):
        run_async(fw.check_and_notify())
        db["next"] = ORDER
        run_async(fw.check_and_notify())
        run_async(fw.check_and_notify())
        run_async(fw.check_and_notify())

        assert len(sent) == 1, "поздравлять с первым заказом можно только один раз"

    def test_marked_before_sending(self, cfg, db, monkeypatch):
        """Пометка ставится ДО отправки: недоступный Telegram должен стоить
        одного пропущенного поздравления, а не поздравления каждые 15 минут."""
        run_async(fw.check_and_notify())
        db["next"] = ORDER

        async def boom(text):
            raise RuntimeError("telegram down")

        monkeypatch.setattr("app.services.notify.send_notification", boom)
        with pytest.raises(RuntimeError):
            run_async(fw.check_and_notify())

        assert cfg[fw.CFG_SEEN]["чистомат"] == "00020"


class TestFailuresAreQuiet:
    def test_firebird_failure_is_not_fatal(self, sent, cfg, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError("Firebird недоступен")

        monkeypatch.setattr(fw, "latest_doc_id", boom)
        assert run_async(fw.check_and_notify()) is False
        assert sent == []
        assert not cfg.get(fw.CFG_SEEN)


class TestMessage:
    def test_it_is_actually_joyful(self):
        text = fw._celebration(ORDER)
        assert text.count("🎉") >= 3
        assert "Поздравляю" in text

    def test_name_comes_from_agbis(self):
        """Название берётся из базы: склад могут переименовать или завести
        «Чистомат 2»."""
        assert "ЧИСТОМАТ 2" in fw._celebration({**ORDER, "sclad_name": "Чистомат 2"})

    def test_date_without_time_is_shown_as_a_date(self):
        """docs.doc_date хранит только дату — «в 00:00» было бы враньём."""
        from datetime import date, datetime
        assert "00:00" not in fw._celebration({**ORDER, "doc_date": date(2026, 8, 14)})
        assert "14.08.2026" in fw._celebration({**ORDER, "doc_date": date(2026, 8, 14)})
        assert "15:30" in fw._celebration({**ORDER, "doc_date": datetime(2026, 8, 14, 15, 30)})
