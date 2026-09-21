"""Тот же человек в разных вакансиях: связь карточек и один опрос вместо двух."""
from __future__ import annotations

import json

import pytest

from app.services import candidate_merge as cm
from app.services import quick_screening as qs
from tests.conftest import run_async


class _C:
    def __init__(self, id, vacancy_id, phone="", resume_id="", state=None):
        self.id = id
        self.vacancy_id = vacancy_id
        self.phone = phone
        self.resume_id = resume_id
        self.name = f"Кандидат {id}"
        self.source = "hh"
        self.external_id = f"neg-{id}"
        self.platform_chat_id = ""
        self.is_paused = False
        self.stage = "новый"
        self.quick_state_json = json.dumps(state) if state else None


class _Vacancy:
    id = 2
    title = "Администратор"
    quick_mode_enabled = True
    quick_questions_json = json.dumps(["Опыт?"], ensure_ascii=False)


class _Db:
    def commit(self):
        pass


class TestIndex:
    def test_links_by_resume_across_vacancies(self):
        a, b = _C(1, 10, resume_id="r1"), _C(2, 20, resume_id="r1")
        idx = cm.cross_vacancy_index([a, b])
        assert [t.id for t in idx[1]] == [2]
        assert [t.id for t in idx[2]] == [1]

    def test_links_by_phone_in_any_format(self):
        a, b = _C(1, 10, phone="+7 (921) 123-45-67"), _C(2, 20, phone="89211234567")
        assert [t.id for t in cm.cross_vacancy_index([a, b])[1]] == [2]

    def test_same_vacancy_is_not_a_cross_link(self):
        """Внутри одной вакансии дубль — это задача слияния, не связи."""
        a, b = _C(1, 10, resume_id="r1"), _C(2, 10, resume_id="r1")
        assert cm.cross_vacancy_index([a, b]) == {}

    def test_no_keys_no_link(self):
        assert cm.cross_vacancy_index([_C(1, 10), _C(2, 20)]) == {}


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def fake_hh_send(token, neg_id, text):
        out.append(neg_id)
        return {}

    async def fake_notify(text):
        return True

    monkeypatch.setattr("app.services.hh_api.send_message", fake_hh_send)
    monkeypatch.setattr("app.services.notify.send_notification", fake_notify)
    monkeypatch.setattr("app.services.candidate_hours.is_within", lambda cfg=None: True)
    return out


def _with_twins(monkeypatch, twins):
    monkeypatch.setattr(cm, "other_vacancy_twins", lambda db, c: twins)


class TestSecondSurveySkipped:
    def test_skipped_when_twin_is_being_screened(self, sent, monkeypatch):
        _with_twins(monkeypatch, [_C(1, 10, resume_id="r1", state={"status": "asking"})])
        c = _C(2, 20, resume_id="r1")
        assert run_async(qs.start_screening(_Db(), c, _Vacancy(), None, "tok")) is False
        assert sent == []
        assert qs.load_state(c) == {}

    def test_skipped_when_twin_already_answered(self, sent, monkeypatch):
        _with_twins(monkeypatch, [_C(1, 10, resume_id="r1", state={"status": "done"})])
        assert run_async(qs.start_screening(_Db(), _C(2, 20, resume_id="r1"), _Vacancy(), None, "tok")) is False

    def test_queued_twin_does_not_block(self, sent, monkeypatch):
        """«queued» — ждём рабочих часов, вопросов ещё никто не задавал."""
        _with_twins(monkeypatch, [_C(1, 10, resume_id="r1", state={"status": "queued"})])
        assert run_async(qs.start_screening(_Db(), _C(2, 20, resume_id="r1"), _Vacancy(), None, "tok")) is True
        assert sent == ["neg-2"]

    def test_manual_start_overrides(self, sent, monkeypatch):
        _with_twins(monkeypatch, [_C(1, 10, resume_id="r1", state={"status": "done"})])
        ok = run_async(qs.start_screening(_Db(), _C(2, 20, resume_id="r1"), _Vacancy(), None, "tok",
                                          allow_twin=True))
        assert ok is True


class _Full(_C):
    """Карточка с полями, которые трогает merge."""
    def __init__(self, id, vacancy_id, stage="новый", state=None, paused=False, **kw):
        super().__init__(id, vacancy_id, state=state, **kw)
        from datetime import datetime
        self.stage = stage
        self.is_paused = paused
        self.email = self.resume_url = self.photo_url = ""
        self.telegram_chat_id = self.telegram_username = ""
        self.age = None
        self.notes = ""
        self.last_message_text, self.last_message_at, self.last_message_from = "", None, ""
        self.call_log_json = None
        self.follow_up_count, self.follow_up_last_sent_at = 0, None
        self.last_inbound_handled_at = self.next_attempt_at = None
        self.has_unread_hh_msg = 0
        self.created_at = self.updated_at = datetime(2026, 9, 1)
        self.channels_json = self.merged_json = None
        self.vacancy = type("V", (), {"title": f"Вакансия {vacancy_id}"})()

    def channels(self):
        return json.loads(self.channels_json) if self.channels_json else []

    def merged_from(self):
        return json.loads(self.merged_json) if self.merged_json else []

    def call_log(self):
        return []


class TestMergeAcrossVacancies:
    def test_primary_keeps_own_stage_survey_and_pause(self):
        w = _Full(1, 10, stage="ответил", state={"status": "done", "answers": [{"q": "A", "a": "1"}]})
        l = _Full(2, 20, stage="отказ", paused=True,
                  state={"status": "done", "answers": [{"q": "B", "a": "2"}, {"q": "C", "a": "3"}]})
        entry = cm.merge_across_vacancies(w, l)
        assert w.stage == "ответил"
        assert w.is_paused is False
        assert qs.load_state(w)["answers"] == [{"q": "A", "a": "1"}]
        assert entry["vacancy_id"] == 20 and entry["vacancy_title"] == "Вакансия 20"
        assert entry["answers"] == [{"q": "B", "a": "2"}, {"q": "C", "a": "3"}]
        assert w.merged_from()[-1]["reason"] == cm.REASON_CROSS_VACANCY
        # переписка второй вакансии — дополнительным каналом
        assert any(ch["external_id"] == "neg-2" for ch in w.channels())

    def test_finished_survey_is_taken_when_primary_had_none(self):
        w = _Full(1, 10)
        l = _Full(2, 20, state={"status": "done", "answers": [{"q": "B", "a": "2"}]})
        cm.merge_across_vacancies(w, l)
        assert qs.load_state(w)["status"] == "done"

    def test_running_survey_of_other_vacancy_is_not_taken(self):
        w = _Full(1, 10)
        l = _Full(2, 20, state={"status": "asking", "answers": []})
        cm.merge_across_vacancies(w, l)
        assert qs.load_state(w) == {}
