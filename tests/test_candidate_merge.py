"""Слияние карточек одного человека.

Кандидаты — настоящие ORM-объекты, но без сессии и без БД: merge() ничего не
запрашивает и не коммитит, так что достаточно конструктора. Так тесты
проверяют и методы модели (channels/merged_from/call_log), через которые
слияние и работает.
"""
import json
from datetime import datetime

import pytest

from app.models.recruitment import Candidate
from app.services import candidate_merge as cm
from app.services.recruitment_stages import (
    STAGE_ANSWERED, STAGE_HIRED, STAGE_NEW, STAGE_RESERVE, STAGE_SCREENING,
)

NOW = datetime(2026, 9, 2, 12, 0, 0)


def cand(**kw):
    base = dict(id=1, vacancy_id=1, name="Иван", source="hh", stage=STAGE_NEW,
                created_at=datetime(2026, 8, 1), follow_up_count=0, is_paused=False,
                has_unread_hh_msg=0)
    base.update(kw)
    return Candidate(**base)


def state(*answers, status="asking"):
    return json.dumps({"status": status, "idx": len(answers),
                       "answers": list(answers)}, ensure_ascii=False)


# ── ключи дубликата ──────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("+7 953 158-85-64", "79531588564"),
    ("8 953 158 85 64", "79531588564"),
    ("79531588564", "79531588564"),
    ("9531588564", "79531588564"),
    ("", ""),
    ("123", ""),
    ("+375 29 123-45-67", ""),      # не 11 цифр с семёркой — ключа нет
])
def test_phone_normalisation(raw, expected):
    assert cm.normalize_phone(raw) == expected


def test_resume_id_ignores_query_params():
    """Ровно та причина, по которой дубли не находились сравнением строк:
    путь резюме один, а ?t= и vacancyId= у откликов разные."""
    a = "https://hh.ru/resume/13be46370010f2fc?t=5496983491&vacancyId=135997822"
    b = "https://hh.ru/resume/13be46370010f2fc?t=5506528508&vacancyId=135367589"
    assert cm.resume_id_from_url(a) == cm.resume_id_from_url(b) == "13be46370010f2fc"


def test_resume_id_of_garbage_is_empty():
    assert cm.resume_id_from_url("https://avito.ru/whatever") == ""
    assert cm.resume_id_from_url(None) == ""


def test_duplicate_key_hh_falls_back_to_url():
    """У карточек, импортированных до появления колонки, resume_id пуст."""
    c = cand(resume_id=None, resume_url="https://hh.ru/resume/abc123?t=1")
    assert cm.duplicate_key_hh(c) == "abc123"


# ── выбор победителя ─────────────────────────────────────────────────────

def test_hh_wins_over_avito():
    """Требование бизнеса: в объединённой карточке опрашивать через hh."""
    hh, avito = cand(id=1, source="hh"), cand(id=2, source="avito")
    assert cm.pick_winner(avito, hh) == (hh, avito)
    assert cm.pick_winner(hh, avito) == (hh, avito)


def test_advanced_stage_wins_within_one_source():
    new = cand(id=1, stage=STAGE_NEW)
    hired = cand(id=2, stage=STAGE_HIRED)
    assert cm.pick_winner(new, hired)[0] is hired


def test_source_beats_stage():
    """Этап у проигравшего не теряется — он попадёт в аудит слияния, а вот
    писать в чат Авито мы можем перестать в любой момент."""
    avito_hired = cand(id=1, source="avito", stage=STAGE_HIRED)
    hh_new = cand(id=2, source="hh", stage=STAGE_NEW)
    assert cm.pick_winner(avito_hired, hh_new)[0] is hh_new


def test_fuller_screening_wins_on_equal_stage():
    thin = cand(id=1, quick_state_json=state("да"))
    full = cand(id=2, quick_state_json=state("да", "шью", "5 лет"))
    assert cm.pick_winner(thin, full)[0] is full


def test_earlier_response_wins_when_all_else_equal():
    old = cand(id=1, created_at=datetime(2026, 6, 1))
    new = cand(id=2, created_at=datetime(2026, 8, 1))
    assert cm.pick_winner(new, old)[0] is old


# ── перенос данных ───────────────────────────────────────────────────────

def test_empty_fields_are_filled_from_loser():
    w = cand(id=1, phone="", age=None, resume_url="")
    l = cand(id=2, phone="+79001234567", age=33, resume_url="https://hh.ru/resume/x")
    cm.merge(w, l, cm.REASON_PHONE, NOW)
    assert w.phone == "+79001234567"
    assert w.age == 33
    assert w.resume_url == "https://hh.ru/resume/x"


def test_filled_fields_are_never_overwritten():
    w = cand(id=1, phone="+79001111111", age=30)
    l = cand(id=2, phone="+79002222222", age=40)
    cm.merge(w, l, cm.REASON_PHONE, NOW)
    assert w.phone == "+79001111111"
    assert w.age == 30


def test_notes_from_both_are_kept():
    w = cand(id=1, notes="звонил, не взял трубку")
    l = cand(id=2, source="avito", notes="писал в чат")
    cm.merge(w, l, cm.REASON_PHONE, NOW)
    assert "звонил, не взял трубку" in w.notes
    assert "писал в чат" in w.notes
    assert "Авито" in w.notes


def test_identical_notes_are_not_duplicated():
    w = cand(id=1, notes="один и тот же текст")
    l = cand(id=2, notes="один и тот же текст")
    cm.merge(w, l, cm.REASON_PHONE, NOW)
    assert w.notes == "один и тот же текст"


def test_further_screening_wins_and_answers_are_not_glued():
    """Ответы из двух чатов нельзя складывать: нумерация вопросов разная,
    и получилась бы смесь ответа на первый с ответом на третий."""
    w = cand(id=1, quick_state_json=state("да"))
    l = cand(id=2, quick_state_json=state("да", "шью сумки", "5 лет", status="done"))
    cm.merge(w, l, cm.REASON_RESUME, NOW)
    assert json.loads(w.quick_state_json)["answers"] == ["да", "шью сумки", "5 лет"]
    assert json.loads(w.quick_state_json)["status"] == "done"


def test_own_screening_is_kept_when_it_is_further():
    w = cand(id=1, quick_state_json=state("а", "б", "в"))
    l = cand(id=2, quick_state_json=state("а"))
    cm.merge(w, l, cm.REASON_RESUME, NOW)
    assert json.loads(w.quick_state_json)["answers"] == ["а", "б", "в"]


def test_latest_message_wins():
    w = cand(id=1, last_message_text="старое", last_message_at=datetime(2026, 8, 1),
             last_message_from="employer")
    l = cand(id=2, last_message_text="свежее", last_message_at=datetime(2026, 8, 20),
             last_message_from="applicant")
    cm.merge(w, l, cm.REASON_RESUME, NOW)
    assert w.last_message_text == "свежее"
    assert w.last_message_from == "applicant"


def test_call_log_is_merged_and_ordered():
    w = cand(id=1, call_log_json=json.dumps([{"at": "2026-08-10T10:00:00", "outcome": "no_answer"}]))
    l = cand(id=2, call_log_json=json.dumps([{"at": "2026-08-05T10:00:00", "outcome": "reached"}]))
    cm.merge(w, l, cm.REASON_PHONE, NOW)
    log = w.call_log()
    assert [e["outcome"] for e in log] == ["reached", "no_answer"]


def test_attempts_are_not_summed():
    """Иначе слияние съедало бы попытки: две карточки по две — и человек
    сразу «не вышел на связь», хотя звонили ему дважды, а не четырежды."""
    w = cand(id=1, follow_up_count=2)
    l = cand(id=2, follow_up_count=2)
    cm.merge(w, l, cm.REASON_PHONE, NOW)
    assert w.follow_up_count == 2


def test_earliest_scheduled_call_is_kept():
    w = cand(id=1, next_attempt_at=datetime(2026, 9, 10, 14, 0))
    l = cand(id=2, next_attempt_at=datetime(2026, 9, 3, 11, 0))
    cm.merge(w, l, cm.REASON_PHONE, NOW)
    assert w.next_attempt_at == datetime(2026, 9, 3, 11, 0)


def test_pause_is_contagious():
    w = cand(id=1, is_paused=False)
    l = cand(id=2, is_paused=True)
    cm.merge(w, l, cm.REASON_PHONE, NOW)
    assert w.is_paused is True


def test_earliest_created_at_survives():
    """Возраст отклика в канбане должен считаться от первого обращения."""
    w = cand(id=1, created_at=datetime(2026, 8, 20))
    l = cand(id=2, created_at=datetime(2026, 6, 23))
    cm.merge(w, l, cm.REASON_RESUME, NOW)
    assert w.created_at == datetime(2026, 6, 23)


# ── каналы ───────────────────────────────────────────────────────────────

def test_loser_chat_becomes_extra_channel():
    w = cand(id=1, source="hh", external_id="555", platform_chat_id="chat-hh")
    l = cand(id=2, source="avito", external_id="u2i-1", platform_chat_id="u2i-1")
    cm.merge(w, l, cm.REASON_PHONE, NOW)
    chans = w.channels()
    assert len(chans) == 1
    assert chans[0]["source"] == "avito"
    assert chans[0]["platform_chat_id"] == "u2i-1"
    assert chans[0]["from_candidate_id"] == 2


def test_primary_channel_is_not_listed_twice():
    w = cand(id=1, source="hh", external_id="555")
    l = cand(id=2, source="hh", external_id="555")
    cm.merge(w, l, cm.REASON_RESUME, NOW)
    assert w.channels() == []


def test_channels_of_loser_are_carried_over():
    """Слияние трёх карточек: второе слияние не должно терять канал,
    подобранный первым."""
    w = cand(id=1, source="hh", external_id="a")
    l = cand(id=2, source="hh", external_id="b",
             channels_json=json.dumps([{"source": "avito", "external_id": "u2i-9",
                                        "platform_chat_id": "u2i-9"}]))
    cm.merge(w, l, cm.REASON_RESUME, NOW)
    got = {(c["source"], c["external_id"]) for c in w.channels()}
    assert got == {("hh", "b"), ("avito", "u2i-9")}


def test_channel_without_any_id_is_skipped():
    """Отклик «по звонку» на Авито: чата нет вовсе, писать некуда."""
    w = cand(id=1, source="hh", external_id="a")
    l = cand(id=2, source="avito", external_id="", platform_chat_id="")
    cm.merge(w, l, cm.REASON_PHONE, NOW)
    assert w.channels() == []


# ── аудит ────────────────────────────────────────────────────────────────

def test_merge_is_recorded():
    w = cand(id=1, source="hh", external_id="555")
    l = cand(id=2, source="avito", name="Иван Петров", stage=STAGE_RESERVE,
             external_id="u2i-1", created_at=datetime(2026, 7, 1))
    cm.merge(w, l, cm.REASON_PHONE, NOW)
    audit = w.merged_from()
    assert len(audit) == 1
    assert audit[0]["candidate_id"] == 2
    assert audit[0]["source"] == "avito"
    assert audit[0]["stage"] == STAGE_RESERVE
    assert audit[0]["reason"] == cm.REASON_PHONE
    assert audit[0]["at"] == NOW.isoformat()


def test_second_merge_appends_to_audit():
    w = cand(id=1)
    cm.merge(w, cand(id=2, source="avito"), cm.REASON_PHONE, NOW)
    cm.merge(w, cand(id=3, source="hh"), cm.REASON_RESUME, NOW)
    assert [e["candidate_id"] for e in w.merged_from()] == [2, 3]


def test_describe_counts_all_responses():
    w = cand(id=1)
    assert cm.describe(w) == ""
    cm.merge(w, cand(id=2, source="avito"), cm.REASON_PHONE, NOW)
    assert cm.describe(w) == "объединено откликов: 2 (Авито)"


def test_broken_json_does_not_break_the_card():
    """Витрина карточки не должна падать из-за мусора в поле."""
    c = cand(id=1, channels_json="{не json", merged_json="[[[", call_log_json="x")
    assert c.channels() == []
    assert c.merged_from() == []
    assert c.call_log() == []


def test_merge_does_not_touch_the_loser():
    """merge() только читает проигравшего — удаление строки остаётся за
    вызывающим кодом, после успешного commit'а победителя."""
    w = cand(id=1, phone="")
    l = cand(id=2, phone="+79001234567", stage=STAGE_SCREENING)
    cm.merge(w, l, cm.REASON_PHONE, NOW)
    assert l.phone == "+79001234567"
    assert l.stage == STAGE_SCREENING


def test_answered_stage_ranks_above_new():
    assert cm.STAGE_RANK[STAGE_ANSWERED] > cm.STAGE_RANK[STAGE_NEW]


# ── этап ─────────────────────────────────────────────────────────────────

def test_human_stage_survives_merge_from_the_loser():
    """Главное, что нельзя потерять: отказ, поставленный руками на карточке
    Авито, при слиянии с карточкой hh, где этап ещё «новый»."""
    w = cand(id=1, source="hh", stage=STAGE_NEW)
    l = cand(id=2, source="avito", stage="отказ")
    cm.merge(w, l, cm.REASON_PHONE, NOW)
    assert w.stage == "отказ"


def test_human_stage_of_winner_is_not_replaced_by_automatic():
    w = cand(id=1, stage=STAGE_RESERVE)
    l = cand(id=2, stage=STAGE_ANSWERED)
    cm.merge(w, l, cm.REASON_RESUME, NOW)
    assert w.stage == STAGE_RESERVE


def test_later_human_decision_wins():
    w = cand(id=1, stage=STAGE_RESERVE, updated_at=datetime(2026, 8, 1))
    l = cand(id=2, stage=STAGE_HIRED, updated_at=datetime(2026, 8, 20))
    cm.merge(w, l, cm.REASON_RESUME, NOW)
    assert w.stage == STAGE_HIRED


def test_automatic_stages_take_the_further_one():
    w = cand(id=1, stage=STAGE_NEW)
    l = cand(id=2, stage=STAGE_ANSWERED)
    cm.merge(w, l, cm.REASON_RESUME, NOW)
    assert w.stage == STAGE_ANSWERED
