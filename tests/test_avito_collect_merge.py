"""Импорт кандидатов Авито: отклики И чаты, а не одно из двух.

Найдено в бою. `_collect_avito` выбирал источник: пробовал платный API
откликов, а при 402 откатывался на чаты мессенджера. Пока подписки не было,
импорт шёл по чатам и заводил карточку каждому, кто написал. Как только
«Максимальный» включили, импорт молча перешёл на API откликов — а тот
отдаёт только формальные отклики: 7 против 67 чатов по одному объявлению.

Переключение задумывалось бесшумным («подписка включилась — платный путь
берёт верх сам»), и оно таким и было: воронка сузилась в девять раз, никто
не заметил, а живые кандидаты остались без ответа.
"""
from __future__ import annotations

import pytest

from app.services import recruitment_sync
from tests.conftest import run_async


def _app(app_id, chat, name, phone="79000000000"):
    return {"external_id": app_id, "name": name, "phone": phone, "age": 30,
            "notes": "Авито отклик", "platform_chat_id": chat}


def _chat(chat, name):
    return {"external_id": chat, "name": name, "phone": "", "age": None,
            "notes": "Авито отклик (через мессенджер)", "platform_chat_id": chat}


@pytest.fixture
def sources(monkeypatch):
    """Задаёт, что вернут оба источника. Значение — список или исключение."""
    state = {"apps": [], "chats": []}

    async def fake_apps(token, uid, vac, **kw):
        if isinstance(state["apps"], Exception):
            raise state["apps"]
        return state["apps"]

    async def fake_chats(token, uid, vac, **kw):
        if isinstance(state["chats"], Exception):
            raise state["chats"]
        return state["chats"]

    monkeypatch.setattr("app.services.avito_api.get_applications_for_vacancy", fake_apps)
    monkeypatch.setattr("app.services.avito_api.get_job_chats", fake_chats)
    return state


def _collect(vac="2353269952"):
    return run_async(recruitment_sync._collect_avito("tok", "21315059", vac))


class TestMerge:
    def test_chat_only_applicants_are_kept(self, sources):
        """Тот самый случай: человек написал в чат без формального отклика."""
        sources["apps"] = [_app("a1", "chat-1", "С откликом")]
        sources["chats"] = [_chat("chat-1", "С откликом"), _chat("chat-2", "Олег")]

        got = _collect()
        assert {c["name"] for c in got} == {"С откликом", "Олег"}

    def test_the_same_person_is_not_duplicated(self, sources):
        sources["apps"] = [_app("a1", "chat-1", "Бугай Егор")]
        sources["chats"] = [_chat("chat-1", "Бугай Егор")]

        got = _collect()
        assert len(got) == 1

    def test_application_wins_over_chat(self, sources):
        """У отклика есть телефон, возраст и резюме — у чата только имя."""
        sources["apps"] = [_app("a1", "chat-1", "Бугай Егор", phone="79002894881")]
        sources["chats"] = [_chat("chat-1", "Егор")]

        [got] = _collect()
        assert got["external_id"] == "a1"
        assert got["phone"] == "79002894881"

    def test_nine_to_one_ratio_from_production(self, sources):
        """Боевые числа по объявлению 2353269952 на момент находки."""
        sources["apps"] = [_app(f"a{i}", f"chat-{i}", f"Отклик {i}") for i in range(7)]
        sources["chats"] = [_chat(f"chat-{i}", f"Чат {i}") for i in range(67)]

        assert len(_collect()) == 67


class TestOneSourceFailing:
    def test_paywall_still_yields_chats(self, sources):
        """Поведение до подписки должно сохраниться."""
        sources["apps"] = ValueError("Авито: доступ к API откликов требует Максимальной подписки")
        sources["chats"] = [_chat("chat-1", "Олег")]

        assert [c["name"] for c in _collect()] == ["Олег"]

    def test_applications_outage_does_not_cost_us_chats(self, sources):
        sources["apps"] = RuntimeError("500 Internal Server Error")
        sources["chats"] = [_chat("chat-1", "Олег")]

        assert len(_collect()) == 1

    def test_chat_outage_does_not_cost_us_applications(self, sources):
        sources["apps"] = [_app("a1", "chat-1", "Бугай Егор")]
        sources["chats"] = RuntimeError("rate limited")

        assert [c["name"] for c in _collect()] == ["Бугай Егор"]

    def test_unrelated_value_error_is_not_swallowed(self, sources):
        """Ошибку, не связанную с подпиской, глушить нельзя — иначе поломка
        конфигурации выглядит как «откликов нет»."""
        sources["apps"] = ValueError("неверный client_id")
        sources["chats"] = []

        with pytest.raises(ValueError):
            _collect()

    def test_both_down_yields_nothing_rather_than_raising(self, sources):
        sources["apps"] = RuntimeError("нет сети")
        sources["chats"] = RuntimeError("нет сети")

        assert _collect() == []


class TestBacklogIsNotSpammed:
    """Слияние источников задним числом вливает в импорт пласт старых людей.

    По боевым данным это 40 чатов, включая организации («2S LAB чистка
    реставрация обуви») и собеседника с именем «пользователь». Разослать им
    «вы ещё в поиске работы?» только потому, что мы сегодня поменяли импорт,
    — ровно то, что запрещает комментарий про первую синхронизацию, просто
    на другом поводе. Опрос положен тем, кто написал ПОСЛЕ прошлого синка.
    """
    from datetime import datetime, timedelta

    SYNCED_AT = datetime(2026, 8, 11, 12, 0, 0)

    def _split(self, created_ats):
        """Предикат берётся из боевого кода, а не переписывается здесь: копия
        условия в тесте уже однажды дала зелёные тесты при сломанном проде."""
        return [t for t in created_ats
                if recruitment_sync.is_new_arrival(t, self.SYNCED_AT)]

    def test_old_chats_are_not_screened(self):
        old = self.SYNCED_AT - self.timedelta(days=30)
        assert self._split([old, old, old]) == []

    def test_genuinely_new_arrival_is_screened(self):
        new = self.SYNCED_AT + self.timedelta(minutes=5)
        assert len(self._split([new])) == 1

    def test_mixed_batch_screens_only_the_new_one(self):
        old = self.SYNCED_AT - self.timedelta(days=3)
        new = self.SYNCED_AT + self.timedelta(minutes=1)
        assert len(self._split([old, new, old, old])) == 1

    def test_missing_date_is_treated_as_backlog(self):
        """Без даты нельзя доказать, что человек новый — молчим."""
        assert self._split([None]) == []

    def test_no_previous_sync_is_backlog(self):
        """Связка ещё ни разу не синхронизировалась — весь импорт исторический."""
        assert recruitment_sync.is_new_arrival(self.SYNCED_AT, None) is False


class TestNameFromApplication:
    """Мессенджер отдаёт имя аккаунта, отклик — настоящие ФИО.

    «Бутте Роман Валерьевич» лежал в воронке как «Олег»: его отклик от
    19 июня не попадал в 30-дневное окно, а чат был жив. Найти человека по
    фамилии было невозможно — что и случилось, когда его искали.
    """

    def test_window_covers_an_application_from_two_months_ago(self):
        """Окно должно перекрывать срок жизни объявления, а не месяц."""
        import inspect
        from app.services import avito_api

        default = inspect.signature(
            avito_api.get_applications_for_vacancy).parameters["days_back"].default
        assert default >= 120, "30 дней обрезали историю: 7 откликов вместо 23"

    def test_application_record_is_the_richer_one(self, sources):
        """Именно поэтому при слиянии побеждает отклик, а не чат."""
        sources["apps"] = [_app("6a3573905870b522d88fabfc", "u2i-x",
                                "Бутте Роман Валерьевич", phone="79533528962")]
        sources["chats"] = [_chat("u2i-x", "Олег")]

        [got] = _collect()
        assert got["name"] == "Бутте Роман Валерьевич"
        assert got["phone"] == "79533528962"


class TestTimezoneRegression:
    """Регрессия из боя: hh отдаёт даты со смещением, а last_synced_at пишется
    через utcnow() без него.

    Сравнение aware с naive — TypeError, и он утопил ВЕСЬ импорт hh:
    исключение ловил общий except уровнем выше, в логе оставалось
    «hh link 3 error: can't compare offset-naive and offset-aware datetimes»,
    кандидаты успевали создаться, а опрос им уже не запускался. Два дня
    откликов на hh прошли молча. У Авито даты наивные — там всё работало,
    что и скрывало поломку.
    """
    from datetime import datetime, timedelta, timezone

    SYNCED = datetime(2026, 8, 12, 12, 0, 0)  # naive UTC, как в базе

    def test_aware_date_does_not_raise(self):
        fresh = self.SYNCED.replace(tzinfo=self.timezone.utc) + self.timedelta(minutes=5)
        assert recruitment_sync.is_new_arrival(fresh, self.SYNCED) is True

    def test_aware_backlog_is_still_backlog(self):
        old = self.SYNCED.replace(tzinfo=self.timezone.utc) - self.timedelta(days=1)
        assert recruitment_sync.is_new_arrival(old, self.SYNCED) is False

    def test_offset_is_honoured_not_stripped(self):
        """09:00 по +03:00 — это 06:00 UTC, то есть РАНЬШЕ синка в 12:00 UTC.
        Просто отбросить tzinfo значило бы посчитать такого кандидата новым."""
        msk = self.datetime(2026, 8, 12, 9, 0, tzinfo=self.timezone(self.timedelta(hours=3)))
        assert recruitment_sync.is_new_arrival(msk, self.SYNCED) is False

    def test_both_naive_still_works(self):
        assert recruitment_sync.is_new_arrival(self.SYNCED + self.timedelta(minutes=1), self.SYNCED) is True
