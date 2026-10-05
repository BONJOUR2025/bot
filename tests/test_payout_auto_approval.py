"""Автоодобрение авансов в пределах лимита с последней зарплаты."""
import asyncio
from types import SimpleNamespace

import pytest

from app.services import payout_auto_approval as aa


@pytest.fixture
def env(monkeypatch):
    state = {"limit": 85000, "since_total": 0.0, "since": "2026-09-15 10:00:00", "status": "active"}
    monkeypatch.setattr(aa, "limit", lambda: state["limit"])
    monkeypatch.setattr(
        "app.data.payout_repository.PayoutRepository",
        lambda *a, **k: SimpleNamespace(advances_since_last_salary=lambda uid: {
            "total": state["since_total"], "count": 1, "since": state["since"]}),
    )
    from app.core.enums import EmployeeStatus

    # Настоящий тип статуса — EmployeeStatus, а не строка: на строке тест
    # проходил, а в проде активная сотрудница считалась неактивной.
    monkeypatch.setattr(
        "app.data.employee_repository.EmployeeRepository",
        lambda *a, **k: SimpleNamespace(get_employee=lambda uid: SimpleNamespace(
            status=EmployeeStatus(state["status"]), advance_auto_limit=state.get("own"))),
    )
    return state


def _req(amount=10000, **kw):
    return {"id": 1, "user_id": "42", "name": "Иванова", "amount": amount, "payout_type": "Аванс",
            "status": "Ожидает", "method": "💳 На карту", "bank": "Т", "card_number": "1", **kw}


def test_within_limit_ok(env):
    env["since_total"] = 75000
    assert aa.check(_req(10000))["ok"]          # ровно 85 000 — можно


def test_over_limit_goes_to_manual(env):
    env["since_total"] = 75001
    info = aa.check(_req(10000))
    assert not info["ok"] and info["reason"].startswith("сверх лимита")


@pytest.mark.parametrize("patch,reason", [
    ({"payout_type": "Зарплата"}, "не аванс"),
    ({"status": "Одобрено"}, "заявка уже обработана"),
])
def test_only_pending_advances(env, patch, reason):
    assert aa.check(_req(**patch))["reason"] == reason


def test_inactive_employee_not_auto(env):
    env["status"] = "inactive"
    assert not aa.check(_req())["ok"]


def test_disabled_with_zero(env):
    env["limit"] = 0
    assert aa.check(_req(1))["reason"] == "автоодобрение выключено"


class _Tg:
    def __init__(self):
        self.bot = object()
        self.calls = []

    async def send_payout_request_to_admin(self, record, extra=""):
        self.calls.append(("request", extra))

    async def send_payout_auto_approved_to_admin(self, record, extra=""):
        self.calls.append(("auto", extra))


def test_auto_approved_notifies_without_buttons(env, monkeypatch):
    approved = []

    async def approve(bot, record, how=""):
        approved.append(record["id"])
        return {"updated": True, "cashier_line": "📬 Чат кассира: Основной кассир"}

    monkeypatch.setattr("app.handlers.admin.payout_actions.approve_request", approve)
    tg = _Tg()
    env["since_total"] = 20000
    assert asyncio.run(aa.handle_new_request(tg, _req(10000))) is True
    assert approved == [1]
    kind, extra = tg.calls[0]
    assert kind == "auto"
    assert extra == "📬 Чат кассира: Основной кассир"   # без сумм авансов с последней ЗП


def test_over_limit_sent_with_buttons_and_reason(env, monkeypatch):
    monkeypatch.setattr("app.handlers.admin.payout_actions.approve_request",
                        lambda *a, **k: pytest.fail("не должно одобряться"))
    tg = _Tg()
    env["since_total"] = 80000
    assert asyncio.run(aa.handle_new_request(tg, _req(10000))) is False
    kind, extra = tg.calls[0]
    assert kind == "request" and extra == "⚠️ Не одобрено автоматически — превышен лимит 85 000 ₽"


def test_already_handled_falls_back_to_manual(env, monkeypatch):
    async def approve(bot, record, how=""):
        return {"updated": False, "cashier_line": ""}

    monkeypatch.setattr("app.handlers.admin.payout_actions.approve_request", approve)
    tg = _Tg()
    assert asyncio.run(aa.handle_new_request(tg, _req(1000))) is False
    assert tg.calls[0][0] == "request"


def test_limit_from_config(monkeypatch):
    for raw, expected in [(None, 85000), ("", 85000), ("50000", 50000), (0, 0), ("мусор", 85000)]:
        monkeypatch.setattr("app.services.config_service.ConfigService.load",
                            lambda self, raw=raw: {"payout_auto_approve_limit": raw})
        assert aa.limit() == expected


def test_own_limit_overrides_global(env):
    env["since_total"] = 20000
    env["own"] = 25000
    info = aa.check(_req(10000))
    assert not info["ok"] and info["limit"] == 25000
    env["own"] = 200000
    env["since_total"] = 150000
    assert aa.check(_req(10000))["ok"]          # больше общего 85 000, но в пределах своего


def test_own_zero_means_never(env):
    env["own"] = 0
    assert aa.check(_req(1))["reason"] == "автоодобрение выключено"


def test_own_limit_works_when_global_disabled(env):
    env["limit"] = 0
    env["own"] = 50000
    assert aa.check(_req(1000))["ok"]
