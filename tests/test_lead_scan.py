"""Отметка через старшего мастера: что разрешено, что нет и в каком порядке пишется."""
from __future__ import annotations

import pytest

from app.services import master_scan_service as scan

MASTER = 110113
OTHER = 110124


def found(status=3, scans=()):
    return {
        "service": {"id": 1, "doc_order_id": 10, "status_id": status, "barcode": "1" * 18, "name": "Набойки",
                    "doc_num": "1-1", "kredit": 1000.0, "current_work_place_id": None},
        "scans": [{"id": i, "date": "2026-09-20T10:00:00", "work_place_id": wp, "user_id": uid, "master": "М."}
                  for i, (wp, uid) in enumerate(scans)],
        "posts": {},
    }


def test_out_on_issued_order_is_allowed_for_lead():
    r = scan.check_lead(found(status=5, scans=[(scan.POST_IN, MASTER)]), "out", MASTER)
    assert r["allowed"] and r["steps"] == ["out"]
    assert any("задним числом" in w for w in r["warnings"])


def test_out_without_in_becomes_in_then_out():
    r = scan.check_lead(found(status=3), "out", MASTER)
    assert r["allowed"] and r["steps"] == ["in", "out"]


def test_repeat_on_same_post_is_never_allowed():
    r = scan.check_lead(found(status=3, scans=[(scan.POST_IN, MASTER), (scan.POST_OUT, OTHER)]), "out", MASTER)
    assert not r["allowed"]
    assert any("переделка" in b for b in r["blockers"])


def test_cancelled_is_blocked_and_in_on_issued_is_pointless():
    assert not scan.check_lead(found(status=7), "out", MASTER)["allowed"]
    assert not scan.check_lead(found(status=5), "in", MASTER)["allowed"]


def test_out_by_another_master_is_warned():
    r = scan.check_lead(found(status=3, scans=[(scan.POST_IN, OTHER)]), "out", MASTER)
    assert r["allowed"] and any("процент уйдут" in w for w in r["warnings"])


def test_lead_confirm_writes_steps_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(scan, "write_enabled", lambda: True)
    monkeypatch.setattr(scan, "lookup", lambda code: found(status=5))

    def fake_exec(con, f, action, uid, now=None, *, lead=None):
        calls.append((action, uid, lead))
        return {"action_id": len(calls)}

    monkeypatch.setattr(scan, "execute_writes", fake_exec)

    class Con:
        def close(self):
            pass

    r = scan.lead_confirm("1" * 18, "out", MASTER, "Смирнов С.", connect=Con)
    assert [c[0] for c in calls] == ["in", "out"]
    assert all(c[1] == MASTER and c[2] == "Смирнов С." for c in calls)
    assert [w["action"] for w in r["written"]] == ["in", "out"] and r["failed"] is None


def test_lead_confirm_dry_run_writes_nothing(monkeypatch):
    monkeypatch.setattr(scan, "write_enabled", lambda: False)
    monkeypatch.setattr(scan, "lookup", lambda code: found(status=3, scans=[(scan.POST_IN, MASTER)]))
    monkeypatch.setattr(scan, "execute_writes", lambda *a, **k: pytest.fail("не должно писать"))
    r = scan.lead_confirm("1" * 18, "out", MASTER, "Смирнов С.")
    assert r["dry_run"] and r["written"] == []


def test_lead_basis_names_the_lead():
    assert "старший мастер Смирнов С." in scan._history_basis("Выход", "Смирнов С.")
    assert "приложения мастера" in scan._history_basis("Выход")
