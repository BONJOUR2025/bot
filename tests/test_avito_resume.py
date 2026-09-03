"""Резюме с Авито.

Раньше с Авито приходили только имя, телефон и возраст, и сводка ИИ
писалась вслепую: «Мастер по коже» с восемью годами стажа получал 30/100 и
вердикт «не подходит» с формулировкой «не указано исправление обуви».
Резюме у Авито есть — оно лежит отдельным документом по `resume_id` из
отклика.

Формат намеренно общий с hh (`hh_api.build_resume_profile`): карточка,
«Прозвон» и сводка уже умеют его читать, и площадка перестаёт быть их
заботой.
"""
import asyncio

import httpx
import pytest

from app.services import avito_api

# Ответ /job/v2/resumes/{id} в том виде, в каком его отдаёт Авито —
# сокращённый до полей, которые мы читаем.
RESUME = {
    "id": 8320798361,
    "title": "Мастер по коже",
    "salary": 70000,
    "description": "Работаю с кожей восемь лет, шью и ремонтирую сумки.",
    "update_time": "2026-08-15T05:41:53Z",
    "address_details": {"location": "Санкт-Петербург", "metro": "Обухово"},
    "params": {
        "age": 51,
        "pol": "Мужской",
        "nationality": "Россия",
        "experience": 8,
        "education": "Незаконченное высшее",
        "schedule": "Полный день",
        "moving": "Невозможен",
        "business_area": "Производство",
        "education_list": [
            {"institution": "ГУТ им. Бонч-Бруевича", "specialty": "Связь",
             "education_stop": 1994},
        ],
        "experience_list": [
            {"company": "ИП", "position": "Мастер по ремонту сумок",
             "work_start": "2016-09-01", "work_finish": "2026-07-01",
             "responsibilities": "Ремонт  и\nреставрация изделий из кожи"},
        ],
    },
}


def test_years_become_months():
    """Авито считает стаж годами, hh — месяцами. Без пересчёта «8» читалось
    бы как восемь месяцев, и кандидат с восемью годами выглядел новичком."""
    assert avito_api.build_resume_profile(RESUME)["total_months"] == 96


def test_core_fields_are_mapped():
    p = avito_api.build_resume_profile(RESUME)
    assert p["title"] == "Мастер по коже"
    assert p["salary"] == {"amount": 70000, "currency": "RUR"}
    assert p["area"] == "Санкт-Петербург"
    assert p["metro"] == "Обухово"
    assert p["schedule"] == "Полный день"
    assert "восемь лет" in p["about"]


def test_experience_matches_the_hh_shape():
    """Ключи те же, что у hh: карточка рисует оба источника одним кодом."""
    job = avito_api.build_resume_profile(RESUME)["experience"][0]
    assert set(job) == {"position", "company", "start", "end", "description"}
    assert job["position"] == "Мастер по ремонту сумок"
    assert job["start"] == "2016-09-01"
    assert job["end"] == "2026-07-01"


def test_education_is_mapped():
    p = avito_api.build_resume_profile(RESUME)
    assert p["education_level"] == "Незаконченное высшее"
    assert p["education"][0]["name"] == "ГУТ им. Бонч-Бруевича"
    assert p["education"][0]["year"] == 1994


def test_empty_resume_gives_empty_profile_not_a_crash():
    p = avito_api.build_resume_profile({})
    assert p["title"] == "" and p["experience"] == []
    assert p["total_months"] is None and p["salary"] is None


def test_garbage_numbers_do_not_crash():
    """У Авито `salary` иногда приходит строкой, а стаж — пустым."""
    p = avito_api.build_resume_profile(
        {"salary": "договорная", "params": {"experience": "много"}})
    assert p["salary"] is None
    assert p["total_months"] is None


def test_zero_salary_is_not_an_expectation():
    assert avito_api.build_resume_profile({"salary": 0})["salary"] is None


def test_long_responsibilities_are_trimmed():
    long = dict(RESUME)
    long["params"] = dict(RESUME["params"])
    long["params"]["experience_list"] = [
        {"position": "п", "company": "к", "responsibilities": "я" * 5000},
    ]
    desc = avito_api.build_resume_profile(long)["experience"][0]["description"]
    assert len(desc) == 1500


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = ""

    def json(self):
        return self._payload


@pytest.fixture
def fake_get(monkeypatch):
    """Подменяет сетевой вызов, сохраняя запрошенный путь."""
    seen = {}

    class Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            seen["url"] = url
            seen["headers"] = headers
            resp = seen["resp"]
            if isinstance(resp, Exception):
                raise resp
            return resp

    monkeypatch.setattr(avito_api.httpx, "AsyncClient", Client)
    return seen


def test_get_resume_returns_a_profile(fake_get):
    fake_get["resp"] = _Resp(200, RESUME)
    p = asyncio.run(avito_api.get_resume("tok", "8320798361"))
    assert p["title"] == "Мастер по коже"
    assert fake_get["url"].endswith("/job/v2/resumes/8320798361")
    assert fake_get["headers"]["Authorization"] == "Bearer tok"


def test_missing_resume_is_none_not_an_error(fake_get):
    """Резюме бывает удалено или скрыто. Анкета украшает карточку — из-за
    неё синхронизация откликов падать не должна."""
    fake_get["resp"] = _Resp(404)
    assert asyncio.run(avito_api.get_resume("tok", "1")) is None


def test_paywalled_resume_is_none(fake_get):
    fake_get["resp"] = _Resp(403)
    assert asyncio.run(avito_api.get_resume("tok", "1")) is None


def test_network_failure_is_none(fake_get):
    fake_get["resp"] = httpx.ConnectError("сеть недоступна")
    assert asyncio.run(avito_api.get_resume("tok", "1")) is None


def test_empty_id_makes_no_request(fake_get):
    fake_get["resp"] = _Resp(200, RESUME)
    assert asyncio.run(avito_api.get_resume("tok", "")) is None
    assert "url" not in fake_get
