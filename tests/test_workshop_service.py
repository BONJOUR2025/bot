"""Цех старшего мастера: разбор услуг на «в работе», ошибки сканов и статистику мастеров."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services import workshop_service as ws

NOW = datetime.now()
TODAY = NOW.replace(hour=12, minute=0, second=0, microsecond=0)


def svc(sid, status, in_uid=None, out_uid=None, in_time=None, out_time=None, **kw):
    base = {"service_id": sid, "doc_num": f"{sid}-1", "name": "Набойки", "kredit": 1000.0,
            "status": status, "in_user_id": in_uid, "out_user_id": out_uid,
            "in_time": in_time.isoformat() if in_time else None,
            "out_time": out_time.isoformat() if out_time else None,
            "in_description": "Агбис-имя", "out_description": "Агбис-имя",
            "duration_min": 60.0, "code": "1.03"}
    base.update(kw)
    return base


@pytest.fixture
def world(monkeypatch):
    state = {"month": [], "details": {}}
    monkeypatch.setattr(ws, "_services", lambda: (state["month"], []))
    monkeypatch.setattr(ws, "_people", lambda: {7: {"employee_id": "e7", "name": "Иванов Иван",
                                                     "short": "Иван И.", "position": "Мастер по ремонту"}})
    monkeypatch.setattr(ws, "_turnstile_today", lambda: {7: TODAY})
    monkeypatch.setattr(ws, "_queue", lambda: [])
    monkeypatch.setattr("app.services.master_bot_service._order_details",
                        lambda ids, with_photos=True: {i: state["details"].get(i, {}) for i in ids})
    monkeypatch.setattr("app.services.masters_service.get_apprentice_stipends", lambda a, b: [])
    return state


def test_wip_and_ready_without_out(world):
    world["month"] = [
        svc(1, "В работе", in_uid=7, in_time=TODAY - timedelta(days=2)),
        svc(2, "В работе", in_uid=7, in_time=TODAY - timedelta(days=1)),   # заказ уже готов
        svc(3, "В работе", in_uid=7, in_time=TODAY),                         # заказ отменён
        svc(4, "Выполнено", in_uid=7, in_time=TODAY - timedelta(days=3)),  # выдан без выхода
    ]
    # Срок считаем от NOW, а не от полудня: с TODAY тест падал каждое утро,
    # когда его запускали раньше 11:00 — «час назад» был ещё в будущем.
    world["details"] = {1: {"order_status_id": 3, "due": NOW - timedelta(hours=1)},
                        2: {"order_status_id": 4}, 3: {"order_status_id": 7}, 4: {"order_status_id": 5}}
    d = ws.build_overview()
    assert [w["service_id"] for w in d["wip"]] == [1]
    assert d["wip"][0]["due_state"] == "overdue"
    assert d["wip"][0]["master"] == "Иванов Иван"
    no_out = {i["service_id"]: i["label"] for i in d["scan_issues"] if i["kind"] == "no_out"}
    assert no_out == {2: "Вход без выхода, а заказ уже готов", 4: "Вход без выхода, а заказ уже выдан"}


def test_too_fast_is_counted_not_listed(world):
    world["month"] = [svc(i, "Выполнено", in_uid=7, out_uid=7, in_time=TODAY, out_time=TODAY,
                          warning_too_fast=True) for i in range(1, 6)]
    world["month"].append(svc(9, "Выполнено", out_uid=7, out_time=TODAY, warning_no_in=True))
    d = ws.build_overview()
    assert [i["kind"] for i in d["scan_issues"]] == ["no_in"]
    m = d["masters"][0]
    assert m["fast"] == 5 and m["issues"] == 1
    assert d["fast_scans_month"] == 5


def test_master_stats_have_no_money_and_know_the_shift(world):
    world["month"] = [
        svc(1, "Выполнено", in_uid=7, out_uid=7, in_time=TODAY - timedelta(hours=3), out_time=TODAY,
            duration_min=180.0),
        svc(2, "Выполнено", in_uid=7, out_uid=7, in_time=TODAY - timedelta(days=3),
            out_time=TODAY - timedelta(days=2), duration_min=5.0),
    ]
    d = ws.build_overview()
    m = d["masters"][0]
    assert (m["today"], m["week"]) == (1, 2)
    assert m["median_min"] == 180  # услуги короче 15 минут в медиану не идут
    assert m["on_shift"] is True
    assert not any("salary" in k for k in m)


def test_position_decides_who_repairs_shoes():
    assert ws._repairs_shoes("Мастер по ремонту") is True
    assert ws._repairs_shoes("Ученик мастера") is True
    assert ws._repairs_shoes("Мастер по изготовлению подошвы") is True
    assert ws._repairs_shoes("Мастер по химчистке") is False
    assert ws._repairs_shoes("Руководитель отдела пошива") is False
    assert ws._repairs_shoes("") is None          # должности нет — решает опыт


def test_advice_skips_dry_cleaning_master():
    """Сканы по ремонту у химчистки бывают (подменял) — в совет он не попадает."""
    queue = [{"service_id": 1, "item_id": 10, "doc_num": "1-1", "name": "Набойки", "kredit": 1000.0,
              "folder": "01. Набойки", "how": "принят на Бестужевской", "urgent": False,
              "waiting_days": 1, "due": None, "due_state": None}]
    services = [{"service_id": i, "out_user_id": uid, "out_time": "2026-09-20T10:00:00",
                 "top_parent_name": "01. Ремонт обуви", "folder_name": "01. Набойки"}
                for i, uid in enumerate([1, 1, 1, 1, 2, 2, 2, 2])]
    stats = {1: {"name": "Химчисткин", "wip": 0, "position": "Мастер по химчистке"},
             2: {"name": "Ремонтников", "wip": 0, "position": "Мастер по ремонту"}}
    people = {1: {"position": "Мастер по химчистке"}, 2: {"position": "Мастер по ремонту"}}
    a = ws._advice(queue, services, stats, None, people)
    assert [m["master_uid"] for m in a["masters"]] == [2]
    assert a["queue"][0]["recommended"]["name"] == "Ремонтников"


def test_tailoring_is_not_workshop():
    assert ws._is_tailoring("4.0 Услуги по инд. пошиву")
    assert not ws._is_tailoring("01. Ремонт обуви")


def test_tailoring_line_rules():
    from app.services.workshop_service import _is_tailoring_line as t

    assert t("Индивидуальный пошив обуви", "1.1 Изделия по инд. пошиву")
    assert t("Изготовление тапочек", "(не входить)")
    assert t("Индивидуальное изготовление ортопедических стелек", "(не входить)")
    assert not t("Изготовление подошвы для обуви", "01. Ремонт обуви")
    assert not t("Изготовление/замена комплектующих", "01. Ремонт обуви")
    assert not t("Замена подошвы", "01. Ремонт обуви")


def test_drop_tailoring_removes_whole_order(monkeypatch):
    from app.services import workshop_service as ws

    monkeypatch.setattr(ws, "_tailoring_docs", lambda nums: {"100-1"})
    rows = [{"doc_num": "100-1", "name": "Изготовление подошвы"}, {"doc_num": "200-2"}]
    assert ws._drop_tailoring(rows) == [{"doc_num": "200-2"}]
