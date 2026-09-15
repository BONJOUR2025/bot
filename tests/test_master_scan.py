"""Вход/выход по бирке из приложения мастера — пробный режим.

Главное здесь три вещи: модуль ничего не пишет в Агбис (только SELECT),
правила постов цеха соблюдены, и план записи совпадает с тем, что клиент
Агбиса пишет при реальном скане (восстановлено по сканам 15.09.2026).
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.api.master_self import create_master_self_router
from app.services import master_bot_service as mbs
from app.services import master_scan_service as scan
from app.services.access_control_service import ResolvedUser

ME = 110133
MASTER = mbs.Master(employee_id="700", name="Корягин Константин", position="Мастер по ремонту", agbis_user_id=ME)
POSTS = {
    1107: {"id": 1107, "name": "1. Ремонт--->ВХОД Цех", "proc": 0.0, "sclad_id": 21021},
    1108: {"id": 1108, "name": "2. Ремонт  ВЫХОД --->Цех", "proc": 23.0, "sclad_id": 21021},
}
NOW = datetime(2026, 9, 16, 12, 0, 0)
BARCODE = "272607000375021003"


def _found(status=1, order_status=1, scans=()):
    return {
        "service": {
            "id": 107349754, "doc_order_id": 10752587, "status_id": status, "current_work_place_id": None,
            "current_sclad_id": 21020, "kredit": 400.0, "kfx": 1.0, "qty_kredit": 1.0, "barcode": BARCODE,
            "name": "Прошивка ***ВНИМАНИЕ", "doc_num": "37502-7",
            "order_status_id": order_status, "order_current_sclad_id": 21020,
        },
        "scans": list(scans),
        "posts": POSTS,
    }


def _scan(post, user_id=ME, master="Корягин К.", when="2026-09-15T14:07:23"):
    return {"id": 1, "date": when, "work_place_id": post, "user_id": user_id, "master": master}


def _table(writes, name):
    return next(w for w in writes if w["table"] == name)


# ── Номер бирки и чтение ──────────────────────────────────────────

def test_barcode_is_reduced_to_digits():
    assert scan.normalize_barcode(" 2726-0700 0375021003 ") == BARCODE


def test_wrong_length_is_rejected_before_touching_the_database():
    with pytest.raises(scan.BarcodeError):
        scan.lookup("12345", connect=lambda: pytest.fail("в базу ходить не должно"))


class _FakeCursor:
    def __init__(self, log):
        self.log = log
        self._rows = []

    def execute(self, sql, params=()):
        self.log.append(sql)
        text = " ".join(sql.split()).lower()
        if "from doc_order_services" in text:
            values = {
                "id": 107349754, "doc_order_id": 10752587, "status_id": 1, "current_work_place_id": None,
                "current_sclad_id": 21020, "kredit": 400, "kfx": 1, "qty_kredit": 1, "barcode": BARCODE,
                "name": "Прошивка", "doc_num": "37502-7", "order_status_id": 1, "order_current_sclad_id": 21020,
            }
            self._rows = [tuple(values[c] for c in scan._SERVICE_COLUMNS)]
        elif "from work_places" in text:
            self._rows = [(1107, "ВХОД Цех", 0, 21021), (1108, "ВЫХОД Цех", 23, 21021)]
        else:
            self._rows = []

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self):
        self.sql = []
        self.closed = False

    def cursor(self):
        return _FakeCursor(self.sql)

    def commit(self):
        pytest.fail("пробный режим не должен ничего фиксировать в Агбисе")

    def close(self):
        self.closed = True


def test_lookup_only_reads_agbis():
    """Пробный режим: в базу уходят только SELECT, никаких INSERT/UPDATE."""
    con = _FakeConnection()
    found = scan.lookup(BARCODE, connect=lambda: con)
    assert found["service"]["doc_num"] == "37502-7"
    assert found["posts"][1108]["proc"] == 23.0
    assert con.sql and all(s.strip().upper().startswith("SELECT") for s in con.sql)
    assert con.closed


# ── Правила постов ────────────────────────────────────────────────

def test_entry_into_a_new_service_is_allowed():
    result = scan.check(_found(), "in", ME)
    assert result == {"allowed": True, "blockers": [], "warnings": []}


def test_exit_without_entry_is_blocked():
    result = scan.check(_found(), "out", ME)
    assert not result["allowed"]
    assert "Входа в цех" in result["blockers"][0]


@pytest.mark.parametrize("status", [5, 6, 7])
def test_issued_closed_or_cancelled_service_is_blocked(status):
    assert not scan.check(_found(status=status), "in", ME)["allowed"]


def test_repeated_entry_warns_about_rework():
    result = scan.check(_found(status=3, scans=[_scan(1107)]), "in", ME)
    assert result["allowed"]
    assert "переделкой" in result["warnings"][0]


def test_exit_after_someone_elses_entry_warns():
    result = scan.check(_found(status=3, scans=[_scan(1107, user_id=110120, master="Цыкунов А.")]), "out", ME)
    assert result["allowed"]
    assert "Цыкунов А." in result["warnings"][0]


def test_suggested_action_follows_the_last_workshop_scan():
    assert scan.suggest_action(_found()) == "in"
    assert scan.suggest_action(_found(scans=[_scan(1107)])) == "out"
    assert scan.suggest_action(_found(scans=[_scan(1107), _scan(1108)])) == "in"


# ── План записи = то, что пишет клиент Агбиса ─────────────────────

def test_entry_plan_matches_a_real_entry_scan():
    writes = scan.plan_writes(_found(), "in", ME, NOW)
    tables = [w["table"] for w in writes]
    assert tables == [
        "USER_SESSION", "USER_SESSION_COWORKS", "USER_SESSION_ACTIONS", "USER_ACTION_HIST",
        "DOC_ORDER_SERVICES", "DOC_ORDER_SERV_HISTORY", "DOCS_ORDER", "DOCS_ORDER_HISTORY",
    ]
    session = _table(writes, "USER_SESSION")["fields"]
    assert session["USER_ID"] == ME and session["WORK_PLACE_ID"] == 1107
    action = _table(writes, "USER_SESSION_ACTIONS")["fields"]
    assert action["DATE_BEG"] == action["DATE_END"]
    assert action["WP_KOEF"] is None and action["SALARY_KOEF"] == 1.0 and action["BARCODE"] == BARCODE
    service = _table(writes, "DOC_ORDER_SERVICES")["fields"]
    assert service["STATUS_ID"] == 3 and service["CURRENT_WORK_PLACE_ID"] == 1107 and service["CURRENT_SCLAD_ID"] == 21021
    assert _table(writes, "DOCS_ORDER")["fields"]["STATUS_ID"] == 3


def test_exit_plan_carries_post_percent_and_leaves_order_alone():
    writes = scan.plan_writes(_found(status=3, order_status=3, scans=[_scan(1107)]), "out", ME, NOW)
    tables = [w["table"] for w in writes]
    assert "DOCS_ORDER" not in tables and "DOCS_ORDER_HISTORY" not in tables
    assert _table(writes, "USER_SESSION_ACTIONS")["fields"]["WP_KOEF"] == 23.0
    service = _table(writes, "DOC_ORDER_SERVICES")["fields"]
    assert service["STATUS_ID"] == 3          # «исполненным» услугу делает салон, не выход из цеха
    assert service["CURRENT_WORK_PLACE_ID"] == 1108


def test_plan_is_always_marked_dry_run_and_empty_when_blocked(monkeypatch):
    monkeypatch.setattr(scan, "lookup", lambda barcode: _found())
    blocked = scan.plan(MASTER, BARCODE, "out", NOW)
    assert blocked["dry_run"] is True and not blocked["allowed"] and blocked["writes"] == []
    allowed = scan.plan(MASTER, BARCODE, "in", NOW)
    assert allowed["dry_run"] is True and allowed["allowed"] and allowed["writes"]


# ── API ────────────────────────────────────────────────────────────

def _user(**kw):
    data = dict(
        id="700", login="koryagin", role_id="master", role_name="Мастер", permissions=[], bot_buttons=[],
        display_name="Константин К.", allowed_employee_ids=["700"], allowed_departments=None,
        employee_id="700", is_master=True,
    )
    data.update(kw)
    return ResolvedUser(**data)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(mbs, "resolve_master", lambda eid: MASTER if eid == "700" else None)
    monkeypatch.setattr(scan, "lookup", lambda barcode: _found() if scan.normalize_barcode(barcode) == BARCODE else None)
    app = FastAPI()
    app.include_router(create_master_self_router(), prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: _user()
    return TestClient(app)


def test_lookup_endpoint_describes_service_and_both_actions(client):
    resp = client.get("/api/masters/me/scan/lookup", params={"barcode": BARCODE})
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["service"]["status_name"] == "Новый"
    assert body["suggested_action"] == "in"
    assert body["checks"]["in"]["allowed"] and not body["checks"]["out"]["allowed"]


def test_preview_endpoint_returns_plan_without_writing(client):
    resp = client.post("/api/masters/me/scan/preview", json={"barcode": BARCODE, "action": "in"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True and body["allowed"]
    assert body["post"]["id"] == 1107
    assert body["writes"][0]["table"] == "USER_SESSION"


def test_unknown_barcode_is_404_with_human_text(client):
    resp = client.get("/api/masters/me/scan/lookup", params={"barcode": "272607000375029999"})
    assert resp.status_code == 404
    assert "не найдена" in resp.json()["detail"]


def test_malformed_barcode_is_400(client):
    resp = client.get("/api/masters/me/scan/lookup", params={"barcode": "123"})
    assert resp.status_code == 400
    assert "18 цифр" in resp.json()["detail"]


def test_unknown_action_is_400(client):
    resp = client.post("/api/masters/me/scan/preview", json={"barcode": BARCODE, "action": "sideways"})
    assert resp.status_code == 400


def test_non_master_cannot_scan(client):
    client.app.dependency_overrides[get_current_user] = lambda: _user(id="703", employee_id="703", is_master=False)
    resp = client.get("/api/masters/me/scan/lookup", params={"barcode": BARCODE})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "not_a_master"
