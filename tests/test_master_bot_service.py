"""Раздел мастера в боте: кого он пускает и чьи деньги показывает.

Самое важное здесь — не арифметика, а два отказа: мастер не должен увидеть
чужой заработок (поэтому сопоставление только по числовому коду Агбиса) и не
должен увидеть уверенный ноль вместо своих денег, когда отчёт в кэше
посчитан старой версией запроса.
"""
from __future__ import annotations

import pytest

from app.services import master_bot_service as mbs


# ── Кого пускаем ──────────────────────────────────────────────────

def test_three_master_positions_are_in_scope():
    assert mbs.is_master_position("Мастер по ремонту")
    assert mbs.is_master_position("Мастер по химчистке")
    assert mbs.is_master_position("Ученик мастера")


def test_sole_maker_is_out_of_scope():
    """«Мастер по изготовлению подошвы» не сканирует на постах мастеров —
    отчёт показал бы ей стабильный ноль, поэтому раздел ей не положен."""
    assert not mbs.is_master_position("Мастер по изготовлению подошвы")


def test_administrator_is_out_of_scope():
    assert not mbs.is_master_position("Администратор")
    assert not mbs.is_master_position("")
    assert not mbs.is_master_position(None)


# ── Опознание мастера ─────────────────────────────────────────────

def _with_users(monkeypatch, tmp_json, users):
    import app.data.employee_repository as er

    monkeypatch.setattr(er, "DATA_FILE", tmp_json("user.json", users))


def test_resolve_master_uses_external_code(monkeypatch, tmp_json):
    """Карточка называется «Константин К.», а в Агбисе он «Корягин К.» —
    строковый матчинг тут промахнулся бы, код Агбиса нет."""
    _with_users(monkeypatch, tmp_json, {
        "1753032859503": {
            "name": "Константин К.",
            "full_name": "Корягин Константин Сергеевич",
            "position": "Мастер по ремонту",
            "external_code": "110133",
        }
    })
    master = mbs.resolve_master("1753032859503")
    assert master is not None
    assert master.agbis_user_id == 110133
    assert master.is_apprentice is False


def test_resolve_master_marks_apprentice(monkeypatch, tmp_json):
    _with_users(monkeypatch, tmp_json, {
        "nb_1": {
            "name": "Мединский А.",
            "full_name": "Мединский Андрей Евгеньевич",
            "position": "Ученик мастера",
            "external_code": "110293",
        }
    })
    master = mbs.resolve_master("nb_1")
    assert master is not None and master.is_apprentice is True


@pytest.mark.parametrize("code", ["", "   ", "не-число", "110133-A"])
def test_resolve_master_refuses_without_usable_code(monkeypatch, tmp_json, code):
    """Без кода Агбиса мы не знаем, чьи сканы показывать. Молча показать
    чужие — единственный отказ, которого эта фича не имеет права допустить,
    поэтому откатываться на сопоставление по фамилии здесь нельзя."""
    _with_users(monkeypatch, tmp_json, {
        "1": {
            "name": "Смирнов С.",
            "full_name": "Смирнов Сергей Петрович",
            "position": "Мастер по ремонту",
            "external_code": code,
        }
    })
    assert mbs.resolve_master("1") is None


def test_resolve_master_refuses_non_master_position(monkeypatch, tmp_json):
    _with_users(monkeypatch, tmp_json, {
        "1": {
            "name": "Юлия 3007",
            "full_name": "Юлия Иванова",
            "position": "Администратор",
            "external_code": "110287",
        }
    })
    assert mbs.resolve_master("1") is None


def test_resolve_master_unknown_employee(monkeypatch, tmp_json):
    _with_users(monkeypatch, tmp_json, {})
    assert mbs.resolve_master("нет-такого") is None


# ── Отбор «моих» услуг ────────────────────────────────────────────

def _master(uid=110133, position="Мастер по ремонту"):
    return mbs.Master(employee_id="1", name="Тест", position=position, agbis_user_id=uid)


def test_mine_matches_ids_arriving_as_floats():
    """Firebird отдаёт user_id через pandas, и он приезжает как 110133.0."""
    services = [
        {"out_user_id": 110133.0, "kredit": 100},
        {"out_user_id": 110120, "kredit": 200},
        {"out_user_id": None, "kredit": 300},
        {"kredit": 400},
    ]
    mine = mbs._mine(services, _master(110133), "out_user_id")
    assert [s["kredit"] for s in mine] == [100]


# ── Защита от устаревшего кэша ────────────────────────────────────

def test_stale_cache_raises_instead_of_reporting_zero(monkeypatch):
    """Записи, посчитанные до появления master_user_id, дали бы пустой
    фильтр и уверенный ноль на экране у мастера. Лучше отказ."""
    monkeypatch.setattr(mbs, "period_range", lambda p, today=None: ("d1", "d2"))
    monkeypatch.setattr(
        "app.services.fdb_cache.get_or_compute",
        lambda report, args: {"services": [{"out_description": "Корягин К.", "kredit": 1}]},
    )
    with pytest.raises(mbs.StaleCacheError):
        mbs._load_services(mbs.PERIOD_MONTH)


def test_empty_report_is_not_treated_as_stale(monkeypatch):
    monkeypatch.setattr(mbs, "period_range", lambda p, today=None: ("d1", "d2"))
    monkeypatch.setattr(
        "app.services.fdb_cache.get_or_compute", lambda report, args: {"services": []}
    )
    assert mbs._load_services(mbs.PERIOD_MONTH) == []


# ── Что считается выплатой ────────────────────────────────────────

SERVICES = [
    {"out_user_id": 110133, "kredit": 1000.0, "master_salary": 200.0,
     "service_group": "Набойки", "warnings": []},
    {"out_user_id": 110133, "kredit": 500.0, "master_salary": 115.0,
     "service_group": "Химчистка", "warnings": ["Нет входа"]},
    {"out_user_id": 999, "kredit": 9999.0, "master_salary": 4000.0,
     "service_group": "Набойки", "warnings": []},
]


def _stub_report(monkeypatch, advances=0.0, stipend=(0.0, 0)):
    monkeypatch.setattr(mbs, "_load_services", lambda period: SERVICES)
    monkeypatch.setattr(mbs, "_advances", lambda eid: advances)
    monkeypatch.setattr(mbs, "_apprentice_stipend", lambda m, df, dt: stipend)


def test_master_is_paid_on_commission(monkeypatch):
    _stub_report(monkeypatch, advances=100.0)
    report = mbs.get_earnings(_master(), mbs.PERIOD_MONTH)
    assert report["payout_basis"] == "accrued"
    assert report["services_count"] == 2          # чужая услуга не попала
    assert report["accrued"] == 315.0
    assert report["kredit"] == 1500.0
    assert report["to_pay"] == 215.0
    assert report["warnings_count"] == 1


def test_apprentice_is_paid_stipend_but_commission_is_shown(monkeypatch):
    """Ученик получает стипендию за дни, но процент по его сканам тоже
    считается — руководителю он нужен как показатель роста."""
    _stub_report(monkeypatch, advances=0.0, stipend=(8000.0, 4))
    report = mbs.get_earnings(_master(position="Ученик мастера"), mbs.PERIOD_MONTH)
    assert report["payout_basis"] == "stipend"
    assert report["stipend"] == 8000.0
    assert report["stipend_days"] == 4
    assert report["accrued"] == 315.0             # справочная цифра на месте
    assert report["to_pay"] == 8000.0             # но платим стипендию


def test_groups_are_sorted_by_earnings(monkeypatch):
    _stub_report(monkeypatch)
    groups = mbs.get_earnings(_master(), mbs.PERIOD_MONTH)["groups"]
    assert [g["group"] for g in groups] == ["Набойки", "Химчистка"]


# ── Потолок аванса ────────────────────────────────────────────────

def test_advance_cap_is_earned_minus_taken(monkeypatch):
    _stub_report(monkeypatch, advances=100.0)
    cap = mbs.get_advance_cap(_master())
    assert cap == {"earned": 315.0, "advances": 100.0, "available": 215.0, "basis": "accrued"}


def test_advance_cap_never_goes_negative(monkeypatch):
    """Авансов взято больше, чем начислено — просить нечего, но и
    отрицательный потолок показывать нельзя."""
    _stub_report(monkeypatch, advances=5000.0)
    assert mbs.get_advance_cap(_master())["available"] == 0.0


def test_apprentice_advance_cap_is_based_on_stipend(monkeypatch):
    _stub_report(monkeypatch, advances=1000.0, stipend=(8000.0, 4))
    cap = mbs.get_advance_cap(_master(position="Ученик мастера"))
    assert cap["basis"] == "stipend"
    assert cap["earned"] == 8000.0
    assert cap["available"] == 7000.0


# ── Подробная сводка: список услуг ────────────────────────────────

def test_earnings_lists_services_newest_first_with_rate_and_day(monkeypatch):
    services = [
        {"out_user_id": 110133, "kredit": 1000.0, "master_salary": 200.0, "service_group": "Набойки",
         "doc_num": "1-3", "name": "Набойки", "out_time": "2026-09-14T10:00:00",
         "in_time": "2026-09-14T09:00:00", "duration_min": 60.0},
        {"out_user_id": 110133, "kredit": 500.0, "master_salary": 115.0, "service_group": "Химчистка",
         "doc_num": "2-3", "name": "Химчистка", "out_time": "2026-09-15T12:00:00"},
        {"out_user_id": 110133, "kredit": 300.0, "master_salary": 60.0, "service_group": None,
         "doc_num": "3-3", "name": "Набойки", "out_time": "2026-09-15T16:00:00"},
        {"out_user_id": 999, "kredit": 9999.0, "master_salary": 4000.0, "doc_num": "чужой",
         "out_time": "2026-09-15T17:00:00"},
    ]
    monkeypatch.setattr(mbs, "_load_services", lambda period: services)
    monkeypatch.setattr(mbs, "_advances", lambda eid: 0.0)

    rows = mbs.get_earnings(_master(), mbs.PERIOD_MONTH)["services"]

    assert [r["doc_num"] for r in rows] == ["3-3", "2-3", "1-3"]   # новые сверху, чужой не попал
    assert rows[0]["rate"] == 0.2
    assert rows[0]["service_group"] == "Другое"
    assert rows[1]["rate"] == 0.23
    assert rows[2]["day"] == "2026-09-14"
    assert rows[2]["duration_min"] == 60.0
