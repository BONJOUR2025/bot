"""Сводка по кандидату: ответы опроса плюс резюме с площадки.

Модель здесь не вызывается — проверяется всё вокруг неё: что в промпт
попадают оба источника, что мусорный ответ не портит карточку и что
отсутствие LLM не роняет опрос.
"""
import json
import re
from datetime import datetime

import pytest

from app.models.recruitment import Candidate
from app.services import candidate_profile as cp

RESUME = {
    "title": "Сборщик кожгалантерейных изделий",
    "salary": {"amount": 75000, "currency": "RUR"},
    "total_months": 46,
    "area": "Санкт-Петербург",
    "education_level": "Среднее специальное",
    "education": [{"name": "Колледж дизайна", "result": "Дизайн", "year": 2023}],
    "skills": ["Работа с кожей", "Швейное оборудование"],
    "languages": ["Русский — Родной"],
    "employment": "Полная занятость",
    "schedule": "Полный день",
    "experience": [
        {"position": "Закройщик", "company": "Кожа и нитки",
         "start": "2022-01-01", "end": None,
         "description": "Раскрой   кожи,\nсборка изделий"},
    ],
}

ANSWERS = [
    {"q": "Есть ли опыт работы с кожей?", "a": "Да, шью сумки вручную"},
    {"q": "Гражданство РФ?", "a": "Да"},
]


def cand(**kw):
    base = dict(id=1, vacancy_id=1, name="Тюлева Диана", source="hh", stage="новый",
                age=31, created_at=datetime(2026, 8, 1),
                resume_profile_json=json.dumps(RESUME, ensure_ascii=False))
    base.update(kw)
    return Candidate(**base)


class _Vacancy:
    title = "Мастер по ремонту обуви и сумок"
    description = ("Мастерская «Бонжур». Приглашаем мастеров, а также кандидатов "
                   "с опытом ручной работы, которые хотят освоить профессию. "
                   "Предоставляем обучение!")
    deal_breakers_json = json.dumps(
        [{"label": "Город проживания", "value": "Санкт-Петербург и Ленинградская область"}],
        ensure_ascii=False)


class _Db:
    def __init__(self):
        self.committed = 0
        self.rolled_back = 0

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1


class _FailingDb(_Db):
    def commit(self):
        raise RuntimeError("БД недоступна")


@pytest.fixture
def llm(monkeypatch):
    """Подменяет и клиент, и сам вызов: возвращает то, что положат в .reply."""
    calls = []

    class Box:
        reply = json.dumps({
            "score": 78,
            "score_reason": "профильный опыт с кожей",
            "recommendation": "invite",
            "recommendation_reason": "стоит позвонить",
            "summary": "Закройщик с опытом почти 4 года.",
            "strengths": ["шьёт вручную", "профильное образование"],
            "red_flags": ["ожидания выше вилки"],
            "salary_expectation": "75 000 ₽",
            "availability": "не указано",
            "tags": ["кожа", "закройщик"],
        }, ensure_ascii=False)

    box = Box()
    monkeypatch.setattr("app.services.llm_client.get_client", lambda cfg: object())

    def fake_chat(cfg, messages, **kw):
        calls.append({"messages": messages, **kw})
        return box.reply

    monkeypatch.setattr("app.services.llm_client.chat", fake_chat)
    box.calls = calls
    return box


# ── подготовка данных для модели ─────────────────────────────────────────

def test_prompt_carries_both_sources():
    prompt = cp.build_prompt(cand(), _Vacancy(), ANSWERS)
    assert "Сборщик кожгалантерейных изделий" in prompt      # из анкеты
    assert "Да, шью сумки вручную" in prompt                  # из опроса
    assert "Мастер по ремонту обуви и сумок" in prompt        # вакансия


def test_prompt_says_plainly_when_there_is_no_resume():
    """Кандидат без анкеты: модель должна это знать, иначе она додумает
    опыт из ответов."""
    prompt = cp.build_prompt(cand(resume_profile_json=None), _Vacancy(), ANSWERS)
    assert "не получена" in prompt


def test_resume_is_formatted_readably():
    text = cp.format_resume(RESUME)
    assert "Ожидания по зарплате: 75000 RUR" in text
    assert "Общий стаж: 3 г. 10 мес." in text
    assert "2022-01-01 — по настоящее время, Кожа и нитки: Закройщик" in text
    # Переносы и двойные пробелы из описания схлопнуты: это одна строка
    # в промпте, а не кусок вёрстки.
    assert "Раскрой кожи, сборка изделий" in text


def test_empty_resume_formats_to_nothing():
    assert cp.format_resume(None) == ""
    assert cp.format_resume({}) == ""


# ── разбор ответа модели ─────────────────────────────────────────────────

def test_profile_is_saved_on_the_candidate(llm):
    c, db = cand(), _Db()
    got = cp.generate(db, c, _Vacancy(), ANSWERS, {})
    assert got["score"] == 78
    assert got["recommendation"] == "invite"
    assert json.loads(c.profile_json)["summary"].startswith("Закройщик")
    assert c.profile_generated_at is not None
    assert db.committed == 1


def test_json_wrapped_in_markdown_is_still_parsed(llm):
    llm.reply = "```json\n{\"score\": 40, \"recommendation\": \"reserve\"}\n```"
    got = cp.generate(_Db(), cand(), _Vacancy(), ANSWERS, {})
    assert got["score"] == 40
    assert got["recommendation"] == "reserve"


def test_out_of_range_score_is_clamped(llm):
    llm.reply = json.dumps({"score": 210, "recommendation": "invite"})
    assert cp.generate(_Db(), cand(), _Vacancy(), ANSWERS, {})["score"] == 100
    llm.reply = json.dumps({"score": -5, "recommendation": "invite"})
    assert cp.generate(_Db(), cand(), _Vacancy(), ANSWERS, {})["score"] == 0


def test_nonsense_score_becomes_none_not_zero(llm):
    """Ноль означал бы «оценили в ноль», а это «не оценили»."""
    llm.reply = json.dumps({"score": "высокий", "recommendation": "invite"})
    assert cp.generate(_Db(), cand(), _Vacancy(), ANSWERS, {})["score"] is None


def test_invented_recommendation_is_dropped(llm):
    """Без балла вердикт брать неоткуда, а выдуманный — не вердикт."""
    llm.reply = json.dumps({"score": "?", "recommendation": "подумать"})
    assert cp.generate(_Db(), cand(), _Vacancy(), ANSWERS, {})["recommendation"] is None


def test_verdict_follows_the_score_not_the_model(llm):
    """Модель распоряжалась вердиктом независимо от собственного балла:
    ставила 0 и «нарушено условие по месту проживания» сапожнику из
    Петербурга, и reject за гражданство, которого нет в жёстких условиях."""
    for score, expected in ((90, "invite"), (75, "invite"), (74, "reserve"),
                            (25, "reserve"), (24, "reject"), (0, "reject")):
        llm.reply = json.dumps({"score": score, "recommendation": "invite"})
        got = cp.generate(_Db(), cand(), _Vacancy(), ANSWERS, {})
        assert got["recommendation"] == expected, f"{score} → {got['recommendation']}"


def test_garbage_reply_produces_no_profile(llm):
    llm.reply = "Извините, я не могу ответить."
    c = cand()
    assert cp.generate(_Db(), c, _Vacancy(), ANSWERS, {}) is None
    assert c.profile_json is None


def test_empty_reply_produces_no_profile(llm):
    llm.reply = ""
    assert cp.generate(_Db(), cand(), _Vacancy(), ANSWERS, {}) is None


def test_lists_are_capped(llm):
    llm.reply = json.dumps({"score": 50, "recommendation": "invite",
                            "strengths": [f"с{i}" for i in range(20)],
                            "tags": [f"t{i}" for i in range(20)]})
    got = cp.generate(_Db(), cand(), _Vacancy(), ANSWERS, {})
    assert len(got["strengths"]) == 6
    assert len(got["tags"]) == 5


# ── устойчивость ─────────────────────────────────────────────────────────

def test_missing_llm_is_not_an_error(monkeypatch):
    """Опрос уже завершён и кандидат уведомлён — падать здесь не из-за чего."""
    monkeypatch.setattr("app.services.llm_client.get_client", lambda cfg: None)
    assert cp.generate(_Db(), cand(), _Vacancy(), ANSWERS, {}) is None


def test_llm_exception_is_swallowed(monkeypatch):
    monkeypatch.setattr("app.services.llm_client.get_client", lambda cfg: object())

    def boom(*a, **kw):
        raise RuntimeError("провайдер лёг")

    monkeypatch.setattr("app.services.llm_client.chat", boom)
    assert cp.generate(_Db(), cand(), _Vacancy(), ANSWERS, {}) is None


def test_failed_commit_rolls_back(llm):
    db = _FailingDb()
    assert cp.generate(db, cand(), _Vacancy(), ANSWERS, {}) is None
    assert db.rolled_back == 1


def test_spend_is_attributed_to_the_screening_bucket(llm):
    cp.generate(_Db(), cand(), _Vacancy(), ANSWERS, {})
    assert llm.calls[0]["employee_id"] == "quick_screening"
    assert llm.calls[0]["feature"] == "candidate_profile"


# ── уведомление ──────────────────────────────────────────────────────────

def test_notification_block_has_verdict_and_summary(llm):
    profile = cp.generate(_Db(), cand(), _Vacancy(), ANSWERS, {})
    text = cp.format_for_notification(profile)
    assert "78/100" in text
    assert "звонить" in text
    assert "Закройщик с опытом почти 4 года." in text
    assert "+ шьёт вручную" in text
    assert "⚠ ожидания выше вилки" in text


def test_notification_block_is_empty_without_a_profile():
    assert cp.format_for_notification(None) == ""


def test_broken_profile_json_does_not_break_the_card():
    assert cand(resume_profile_json="{не json").resume_profile() is None
    assert cand(resume_profile_json="[1,2]").resume_profile() is None


def test_discriminatory_fields_never_reach_the_model():
    """Модель поставила «возраст» красным флагом 65-летнему мастеру с 26
    годами стажа по профилю. Запрет на выходе держал формулировки, но не
    балл, поэтому признак убран из входа: возраст в промпт не попадает,
    даже когда он известен."""
    prompt = cp.build_prompt(cand(age=65), _Vacancy(), ANSWERS)
    assert "65" not in prompt
    assert "Возраст" not in prompt


def test_prompt_carries_the_vacancy_text_not_just_its_title():
    """Раньше уходил только заголовок, и «нет опыта ремонта обуви» стало
    причиной 34 отказов из 63 — при том что вакансия обещает обучение."""
    prompt = cp.build_prompt(cand(), _Vacancy(), ANSWERS)
    assert "Предоставляем обучение" in prompt
    assert "хотят освоить профессию" in prompt


def test_prompt_lists_deal_breakers():
    prompt = cp.build_prompt(cand(), _Vacancy(), ANSWERS)
    assert "Город проживания" in prompt
    assert "Ленинградская область" in prompt


def test_vacancy_without_deal_breakers_adds_no_section():
    class Bare:
        title = "Мастер"
        description = "Описание"
        deal_breakers_json = None

    assert "Жёсткие условия" not in cp.format_vacancy(Bare())


def test_broken_deal_breakers_json_does_not_break_the_prompt():
    class Broken:
        title = "Мастер"
        description = "Описание"
        deal_breakers_json = "{не json"

    assert "Мастер" in cp.format_vacancy(Broken())


def test_missing_resume_is_stated_as_missing_data():
    """«Нет анкеты» — это отсутствие сведений, а не отсутствие опыта: на
    32 карточках Авито модель писала «опыт не подтверждён» просто потому,
    что резюме не забиралось."""
    prompt = cp.build_prompt(cand(resume_profile_json=None), _Vacancy(), ANSWERS)
    assert "не отсутствие опыта" in prompt


def test_missing_answers_are_stated_as_not_screened():
    prompt = cp.build_prompt(cand(), _Vacancy(), [])
    assert "опрос не пройден" in prompt


def test_rubric_has_anchored_bands():
    """Без якорей балл был случаен: одни и те же данные словами давали
    70/«звонить» одному и 30/«отказ» другому."""
    for anchor in ("80-100", "60-79", "40-59", "20-39", "0-19"):
        assert anchor in cp.SYSTEM


def test_rubric_names_adjacent_trades_as_profile_experience():
    """Первая же прогонка дала «Мастеру по коже» с восемью годами стажа 40
    баллов с формулировкой «нет опыта ремонта обуви»: без перечисления
    профессий модель читает профиль по названию вакансии буквально."""
    for trade in ("швея", "закройщик", "сапожник", "мастер по коже", "реставратор"):
        assert trade in cp.SYSTEM
    # Промпт свёрстан по ширине, поэтому фразы рвутся переносами.
    flat = re.sub(r"\s+", " ", cp.SYSTEM).lower()
    assert "не требуй, чтобы где-то буквально стояло" in flat


def test_missing_screening_does_not_lower_the_score():
    assert "не снижай за это балл" in cp.SYSTEM


def test_rubric_forbids_rejecting_for_missing_experience():
    flat = re.sub(r"\s+", " ", cp.SYSTEM)
    assert "Ни нехватка опыта, ни город, ни смена профессии основанием для reject" in flat


def test_model_does_not_decide_deal_breakers_itself():
    """Модель выставила 0 и «нарушено жёсткое условие по месту проживания»
    сапожнику, который живёт в Санкт-Петербурге. Расхождение она теперь
    только показывает, а решает человек."""
    flat = re.sub(r"\s+", " ", cp.SYSTEM)
    assert "жёсткие условия не проверяешь" in flat
    assert "ни город" in flat


def test_scoring_does_not_use_the_cheap_chat_model(llm):
    """Модель бота по умолчанию — gpt-4.1-nano: для реплик в чате её
    хватает, а рубрику из пяти полос она не удерживает и противоречит сама
    себе (называет швейное дело профильным и ставит за него 10)."""
    cp.generate(_Db(), cand(), _Vacancy(), ANSWERS, {})
    assert llm.calls[-1]["model"] == cp.MODEL
    assert "nano" not in cp.MODEL


def test_scoring_is_deterministic(llm):
    """Одно и то же резюме получало 30, 53, 50, 60 и 39 в пяти прогонках:
    на провайдерской температуре балл нельзя использовать для сравнения."""
    cp.generate(_Db(), cand(), _Vacancy(), ANSWERS, {})
    assert llm.calls[-1]["temperature"] == 0


def test_parse_keeps_questions_for_the_call(llm):
    llm.reply = json.dumps({
        "score": 50, "recommendation": "reserve", "summary": "—",
        "to_ask": ["сколько лет работал с кожей", "готов ли на 5/2",
                   "лишний", "ещё лишний", "пятый"],
    }, ensure_ascii=False)
    profile = cp.generate(_Db(), cand(), _Vacancy(), ANSWERS, {})
    assert profile["to_ask"][:2] == ["сколько лет работал с кожей", "готов ли на 5/2"]
    assert len(profile["to_ask"]) == 4


def test_profile_records_what_it_was_built_from(llm):
    """Оценка по одной анкете не равна оценке после опроса, и в карточке
    это должно быть видно."""
    assert cp.generate(_Db(), cand(), _Vacancy(), ANSWERS, {})["basis"] == "resume+answers"
    assert cp.generate(_Db(), cand(), _Vacancy(), [], {})["basis"] == "resume"
    bare = cand(resume_profile_json=None)
    assert cp.generate(_Db(), bare, _Vacancy(), ANSWERS, {})["basis"] == "answers"
    assert cp.generate(_Db(), bare, _Vacancy(), [], {})["basis"] == "none"
