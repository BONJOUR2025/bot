"""Кабинет мастера: /api/masters/me/* отдаёт только данные самого мастера.

Главное здесь — откуда берётся id: из сессии, а не из запроса. Подставить
чужой сотрудник не может, потому что запрос этот id просто не читает.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.api import master_self
from app.api.master_self import create_master_self_router
from app.services import master_bot_service as mbs
from app.services.access_control_service import ResolvedUser

MASTER = mbs.Master(
    employee_id="700", name="Корягин Константин", position="Мастер по ремонту", agbis_user_id=110133,
)


def _user(**kw):
    data = dict(
        id="700", login="koryagin", role_id="master", role_name="Мастер",
        permissions=[], bot_buttons=[], display_name="Константин К.",
        allowed_employee_ids=["700"], allowed_departments=None,
        employee_id="700", is_master=True,
    )
    data.update(kw)
    return ResolvedUser(**data)


def _client(user):
    app = FastAPI()
    app.include_router(create_master_self_router(), prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture
def calls(monkeypatch):
    seen: list[tuple] = []
    monkeypatch.setattr(mbs, "resolve_master", lambda eid: MASTER if eid == "700" else None)

    def earnings(master, period):
        seen.append(("earnings", master.employee_id, period))
        return {"period": period, "accrued": 315.0, "is_apprentice": False}

    monkeypatch.setattr(mbs, "get_earnings", earnings)
    monkeypatch.setattr(
        mbs, "get_wip",
        lambda master, refresh=False: [{"doc_num": "37209-7", "kredit": 2100.0}],
    )
    monkeypatch.setattr(
        mbs, "get_advance_cap",
        lambda master: {"earned": 315.0, "advances": 0.0, "available": 315.0, "basis": "accrued"},
    )
    return seen


def test_earnings_for_own_master(calls):
    resp = _client(_user()).get("/api/masters/me/earnings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["accrued"] == 315.0
    assert body["name"] == "Корягин Константин"
    assert calls == [("earnings", "700", "month")]


def test_previous_month(calls):
    resp = _client(_user()).get("/api/masters/me/earnings", params={"period": "prev_month"})
    assert resp.status_code == 200
    assert calls == [("earnings", "700", "prev_month")]


def test_unwarmed_period_is_rejected(calls):
    """Квартал в кэше не прогрет — запрос ушёл бы живьём в Firebird."""
    resp = _client(_user()).get("/api/masters/me/earnings", params={"period": "quarter"})
    assert resp.status_code == 400
    assert calls == []


def test_id_comes_from_session_not_from_query(calls):
    resp = _client(_user()).get("/api/masters/me/earnings", params={"employee_id": "999"})
    assert resp.status_code == 200
    assert calls[0][1] == "700"


def test_account_without_employee_is_forbidden(calls):
    client = _client(_user(employee_id=None))
    for path in ("earnings", "wip", "advance-cap"):
        assert client.get(f"/api/masters/me/{path}").status_code == 403


def test_employee_who_is_not_a_master_gets_404(calls):
    client = _client(_user(id="703", employee_id="703", is_master=False))
    for path in ("earnings", "wip", "advance-cap"):
        resp = client.get(f"/api/masters/me/{path}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "not_a_master"


def test_stale_cache_is_503_with_human_text(monkeypatch, calls):
    """Кэш, посчитанный до появления master_user_id, — не ноль, а «обновляется»."""
    def stale(master, period):
        raise mbs.StaleCacheError("old cache")

    monkeypatch.setattr(mbs, "get_earnings", stale)
    resp = _client(_user()).get("/api/masters/me/earnings")
    assert resp.status_code == 503
    assert "обновляются" in resp.json()["detail"]


def test_wip_and_advance_cap(calls):
    client = _client(_user())
    wip = client.get("/api/masters/me/wip")
    assert wip.status_code == 200
    assert wip.json()["items"][0]["doc_num"] == "37209-7"
    cap = client.get("/api/masters/me/advance-cap")
    assert cap.status_code == 200
    assert cap.json()["available"] == 315.0


def test_far_thumbs_are_deferred_to_a_second_request(calls, monkeypatch):
    """Миниатюры дальних строк не едут в первом ответе: у мастера с сорока
    работами они весили втрое больше самого списка."""
    rows = [
        {"service_id": i, "doc_num": f"{i}-7", "kredit": 100.0,
         "photos": [{"id": i, "md5": "x", "thumb": f"data:image/jpeg;base64,{i}"}]}
        for i in range(12)
    ]
    monkeypatch.setattr(mbs, "get_wip", lambda master, refresh=False: rows)
    client = _client(_user())

    items = client.get("/api/masters/me/wip").json()
    assert items["thumbs_deferred"] == 12 - master_self.WIP_INLINE_THUMBS
    assert items["items"][0]["photos"][0]["thumb"] is not None
    assert items["items"][-1]["photos"][0]["thumb"] is None
    assert rows[-1]["photos"][0]["thumb"] is not None   # кэш сервиса не испорчен

    thumbs = client.get("/api/masters/me/wip/thumbs").json()["thumbs"]
    assert thumbs["11"] == "data:image/jpeg;base64,11"
    assert "0" not in thumbs


def test_photo_of_someone_elses_order_is_not_served(calls, monkeypatch):
    checked = []

    def can_see(uid, photo_id, md5):
        checked.append((uid, photo_id, md5))
        return False

    monkeypatch.setattr(mbs, "master_can_see_photo", can_see)
    resp = _client(_user()).get("/api/masters/me/photos/555/full", params={"md5": "ABC"})
    assert resp.status_code == 404
    assert checked == [(110133, 555, "ABC")]   # id мастера — из сессии


def test_photo_of_own_order_comes_from_storage(calls, monkeypatch):
    from app.services import agbis_photos, firebird_service

    monkeypatch.setattr(mbs, "master_can_see_photo", lambda uid, pid, md5: True)

    class _Fb:
        def get_order_photo_full_from_db(self, photo_id):
            return None

    monkeypatch.setattr(firebird_service, "get_firebird_service", lambda: _Fb())
    monkeypatch.setattr(agbis_photos, "get_photo", lambda md5: b"\xff\xd8jpeg")
    resp = _client(_user()).get("/api/masters/me/photos/555/full", params={"md5": "ABC"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg" and resp.content == b"\xff\xd8jpeg"
