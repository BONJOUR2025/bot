"""Извлечение времени звонка из сообщения кандидата.

Найдено в бою: кандидаты назначают время сами — «Завтра в 14:00» (Бугай),
«часа в 3 будет удобно» (Федотов), «могу в любое время» (Кованова). Раньше
это оседало обычным уведомлением, и дальше всё держалось на памяти
человека. Не удержалось: Бугаю никто не позвонил, заметили через сутки.

Главное свойство, которое фиксируют тесты: **при неуверенности молчим**.
Выдуманное напоминание хуже отсутствующего, потому что ему поверят.
"""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from app.services import call_time


NOW = datetime(2026, 8, 13, 12, 0)  # четверг


@pytest.fixture
def model(monkeypatch):
    """Подменяет ответ модели. Значение — dict или строка."""
    box = {"reply": None}

    def fake_chat(cfg, messages, **kw):
        r = box["reply"]
        return r if isinstance(r, str) else json.dumps(r)

    monkeypatch.setattr("app.services.llm_client.chat", fake_chat)
    monkeypatch.setattr("app.services.llm_client.get_client", lambda cfg: object())
    return box


class TestPrefilter:
    """Без намёка на время модель не вызывается вовсе — это и точность, и
    деньги: на обычных ответах вроде «Да» лишний вызов не нужен."""

    def test_obvious_time_phrases_pass(self):
        for t in ("Завтра в 14:00", "часа в 3 будет удобно", "после обеда",
                  "в 17", "можем в понедельник", "сегодня вечером"):
            assert call_time.looks_like_time(t) is True, t

    def test_plain_answers_do_not(self):
        for t in ("Да", "Нет, такого опыта пока нет", "Работаю с кожей 8 лет"):
            assert call_time.looks_like_time(t) is False, t

    def test_model_not_called_without_hint(self, monkeypatch):
        def boom(*a, **kw):
            pytest.fail("модель не должна вызываться без намёка на время")
        monkeypatch.setattr("app.services.llm_client.get_client", boom)
        assert call_time.extract("Да", {}, now=NOW) is None


class TestExtraction:
    def test_tomorrow_at_fourteen(self, model):
        model["reply"] = {"day": "tomorrow", "time": "14:00"}
        d, t = call_time.extract("Завтра в 14:00", {}, now=NOW)
        assert (d.isoformat(), t.strftime("%H:%M")) == ("2026-08-14", "14:00")

    def test_today_at_three(self, model):
        model["reply"] = {"day": "today", "time": "15:00"}
        d, t = call_time.extract("часа в 3 будет удобно", {}, now=NOW)
        assert (d.isoformat(), t.strftime("%H:%M")) == ("2026-08-13", "15:00")


class TestSilenceOnDoubt:
    def test_no_time_named(self, model):
        model["reply"] = {"day": None, "time": None}
        assert call_time.extract("Завтра посмотрю", {}, now=NOW) is None

    def test_time_already_passed_today_moves_to_tomorrow(self, model):
        """«после 17», написанное в 18:00, разумнее понять как завтра."""
        model["reply"] = {"day": None, "time": "09:00"}
        d, t = call_time.extract("в 9 удобно", {}, now=NOW)
        assert d.isoformat() == "2026-08-14"

    def test_garbage_reply_is_ignored(self, model):
        model["reply"] = "извините, не понял"
        assert call_time.extract("Завтра в 14:00", {}, now=NOW) is None

    def test_broken_date_format_is_ignored(self, model):
        model["reply"] = {"day": "завтра", "time": "14 часов"}
        assert call_time.extract("Завтра в 14:00", {}, now=NOW) is None

    def test_model_failure_is_not_fatal(self, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError("provider down")
        monkeypatch.setattr("app.services.llm_client.get_client", lambda cfg: object())
        monkeypatch.setattr("app.services.llm_client.chat", boom)
        assert call_time.extract("Завтра в 14:00", {}, now=NOW) is None

    def test_no_model_means_no_guessing(self, monkeypatch):
        monkeypatch.setattr("app.services.llm_client.get_client", lambda cfg: None)
        assert call_time.extract("Завтра в 14:00", {}, now=NOW) is None

    def test_slightly_past_within_tolerance_is_kept(self, model):
        """Пока сообщение шло и обрабатывалось, названное время могло чуть
        отстать. Минутный зазор не должен отменять договорённость."""
        model["reply"] = {"day": "today", "time": "11:58"}
        assert call_time.extract("в 11:58", {}, now=NOW) is not None


class TestDayArithmeticIsOurs:
    """Даты считает код, а не модель.

    Замер на боевой модели: на просьбу вернуть готовую дату она выдала
    «2023-08-14» вместо 2026 года и назвала 18 августа понедельником, хотя
    это вторник. Слово «завтра» при этом распознаётся безошибочно — его и
    спрашиваем, календарь считаем сами.
    """
    from datetime import time as _t

    def test_weekday_resolves_to_the_next_one(self):
        # NOW — четверг 13.08.2026, ближайший понедельник 17-е
        d = call_time._resolve_day("monday", self._t(10, 0), NOW)
        assert d.isoformat() == "2026-08-17"
        assert d.weekday() == 0

    def test_same_weekday_means_next_week(self):
        """«В четверг», сказанное в четверг, — это следующий четверг."""
        d = call_time._resolve_day("thursday", self._t(10, 0), NOW)
        assert d.isoformat() == "2026-08-20"

    def test_tomorrow_and_day_after(self):
        assert call_time._resolve_day("tomorrow", self._t(9, 0), NOW).isoformat() == "2026-08-14"
        assert call_time._resolve_day("day_after", self._t(9, 0), NOW).isoformat() == "2026-08-15"

    def test_no_day_named_means_today_if_time_is_ahead(self):
        assert call_time._resolve_day(None, self._t(18, 0), NOW).isoformat() == "2026-08-13"

    def test_no_day_named_means_tomorrow_if_time_has_passed(self):
        assert call_time._resolve_day(None, self._t(9, 0), NOW).isoformat() == "2026-08-14"


class TestInventedTimeIsRejected:
    """Модель охотно выдумывает час, которого в сообщении не было.

    Замер: на «можем завтра созвониться» — где времени нет вовсе — она
    уверенно вернула 14:00. Напоминание на час, который никто не назначал,
    хуже отсутствия напоминания: ему поверят и придут не вовремя.
    """

    def test_day_without_hour_is_rejected(self, model):
        model["reply"] = {"day": "tomorrow", "time": "14:00"}
        assert call_time.extract("можем завтра созвониться", {}, now=NOW) is None

    def test_digit_counts_as_named_hour(self, model):
        model["reply"] = {"day": "tomorrow", "time": "17:00"}
        assert call_time.extract("завтра после 17 смогу", {}, now=NOW) is not None

    def test_daypart_counts_as_named_hour(self, model):
        model["reply"] = {"day": "day_after", "time": "18:00"}
        assert call_time.extract("послезавтра вечером", {}, now=NOW) is not None


class TestTimePrepositions:
    """Предлог времени + число — самая частая форма в переписках.

    «после 17 смогу» не подходило ни под один шаблон предфильтра, и до
    модели дело не доходило вовсе: сообщение молча считалось «без времени».
    Вместе с ним пропадали «к 18 подъеду», «до 19 свободен», «с 15 могу».
    """

    def test_prepositions_are_recognised(self):
        for t in ("после 17 смогу", "к 18 подъеду", "до 19 свободен",
                  "с 15 могу", "около 16 наберите", "в 17"):
            assert call_time.looks_like_time(t) is True, t

    def test_bare_number_about_experience_is_not_a_time(self):
        """Голое число в предфильтр не берём: иначе модель начнёт искать
        время в рассказе про стаж — и находить там, где его нет."""
        for t in ("Работаю мастером по коже 8 лет", "опыт 2 года",
                  "делал 15 пар в смену"):
            assert call_time.looks_like_time(t) is False, t

    def test_after_seventeen_resolves_to_today(self, model):
        model["reply"] = {"day": None, "time": "17:00"}
        d, t = call_time.extract("после 17 смогу", {}, now=NOW)
        assert (d.isoformat(), t.strftime("%H:%M")) == ("2026-08-13", "17:00")
