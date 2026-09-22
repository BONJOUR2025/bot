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
    world["details"] = {1: {"order_status_id": 3, "due": TODAY - timedelta(hours=1)},
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
